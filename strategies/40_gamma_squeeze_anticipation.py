#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
策略40：期权Gamma挤压预判与收益增强策略
基于标的价格快速变动时Gamma急剧收缩（short gamma风险）
结合期权持仓gamma分布，预判Gamma挤压（Gamma Squeeze）发生概率
在低Delta/高Gamma区域布局高杠杆买权，同时用卖方策略对冲成本
"""

import numpy as np
import pandas as pd
from tqsdk import TqApi, TqAuth, TqOption, TargetPosTask

# ========== 策略参数 ==========
UNDERLYING = "SHFE.rb2505"           # 标的
INIT_PORTFOLIO = 2000000

# Gamma挤压预判参数
PRICE_CHANGE_WINDOW = 10             # 价格变化窗口（分钟）
PRICE_SPIKE_THRESHOLD = 0.015        # 价格异动阈值（1.5%）
GAMMA_HIGH_THRESHOLD = 0.05          # 高Gamma阈值

# 期权筛选
STRIKE_RANGE_PCT = 0.10              # 执行价范围（ATM±10%）
DTE_MIN = 3                          # 最小剩余期限（天）
DTE_MAX = 30                         # 最大剩余期限（天）
LOT_SIZE = 1                         # 每批次手数

# ========== Gamma Squeeze预判指标 ==========
def calc_gamma_exposure(option_positions, spot):
    """
    计算组合整体Gamma暴露
    正值 = Long Gamma（价格上涨更易持续）
    负值 = Short Gamma（价格反转风险大）
    """
    total_gamma = 0.0
    for pos in option_positions:
        strike = pos.get("strike", spot)
        dte = pos.get("dte", 15)
        iv = pos.get("iv", 0.20)
        position_type = pos.get("type", "call")
        direction = pos.get("direction", 1)
        lots = pos.get("lots", 1)
        if dte <= 0 or dte > 60:
            continue
        moneyness = (spot - strike) / strike if position_type == "call" else (strike - spot) / spot
        abs_moneyness = abs(moneyness)
        atm_factor = np.exp(-abs_moneyness ** 2 / 0.02)
        dte_factor = 1.0 / np.sqrt(dte / 30)
        base_gamma = atm_factor * dte_factor * iv * lots * direction
        total_gamma += base_gamma
    return total_gamma

def detect_price_momentum(klines_5min, window=10):
    """检测短期价格动量"""
    if len(klines_5min.close) < window + 1:
        return 0.0
    prices = klines_5min.close[-window:]
    recent_change = (prices[-1] / prices[0]) - 1
    return recent_change

def estimate_gamma_squeeze_prob(price_momentum, gamma_exposure, gamma_history):
    """综合预判Gamma挤压发生概率"""
    if len(gamma_history) < 20:
        return 0.5
    gamma_mean = np.mean(gamma_history[-20:])
    momentum_signal = min(1.0, abs(price_momentum) / 0.02)
    short_gamma_risk = 0.0
    if gamma_exposure < -0.01:
        short_gamma_risk = min(1.0, abs(gamma_exposure) / (abs(gamma_mean) + 1e-8))
    squeeze_prob = 0.5 * momentum_signal + 0.5 * short_gamma_risk
    return squeeze_prob

# ========== 策略主体 ==========
def main():
    api = TqApi(auth=TqAuth("auto", "auto"))
    target_pos = TargetPosTask(api)

    print(f"[策略40] Gamma挤压预判与收益增强策略启动 | 标的: {UNDERLYING}")

    underlying_quote = api.get_quote(UNDERLYING)
    spot_price = underlying_quote.last_price

    kline_5min = api.get_kline_serial(UNDERLYING, 300, data_length=200)
    print(f"[策略40] ATM执行价: {spot_price:.2f}")

    option_positions = []
    gamma_history = []
    tick_count = 0

    while True:
        api.wait_update()
        tick_count += 1
        spot = underlying_quote.last_price
        if spot <= 0 or np.isnan(spot):
            continue
        if tick_count % 10 != 0:
            continue

        price_momentum = detect_price_momentum(kline_5min, 10)
        gamma_exposure = calc_gamma_exposure(option_positions, spot)
        gamma_history.append(gamma_exposure)
        squeeze_prob = estimate_gamma_squeeze_prob(price_momentum, gamma_exposure, gamma_history)

        print(f"[策略40] Tick {tick_count} | Spot={spot:.2f} | "
              f"动量={price_momentum:.3f} | Gamma={gamma_exposure:.4f} | "
              f"Squeeze Prob={squeeze_prob:.2%}")

        # 高概率Gamma挤压：平Short Gamma
        if squeeze_prob > 0.7 and abs(price_momentum) > PRICE_SPIKE_THRESHOLD:
            print(f"         >>> 高危: Gamma挤压预警！预判概率={squeeze_prob:.1%}")
            print(f"         >>> 行动: 平仓Short Gamma，卖方减仓")
            for pos in option_positions[:]:
                if pos["direction"] == -1:
                    print(f"         >>> 平仓 Short {pos['type']} K={pos['strike']}")
                    option_positions.remove(pos)

        # 低概率时期：构建Short Strangle收益增强
        elif squeeze_prob < 0.3:
            atm_strike = round(spot / 10) * 10
            call_strike = atm_strike + int(spot * 0.03 / 10) * 10
            put_strike = atm_strike - int(spot * 0.03 / 10) * 10
            existing_strikes = [p["strike"] for p in option_positions]
            if call_strike not in existing_strikes and put_strike not in existing_strikes:
                greeks_now = calc_gamma_exposure(option_positions, spot)
                if greeks_now > -0.05:
                    print(f"         >>> 收益增强: Short Strangle Call={call_strike} Put={put_strike}")
                    option_positions.append({
                        "symbol": f"OPT-C-{call_strike}", "strike": call_strike,
                        "type": "call", "direction": -1, "lots": LOT_SIZE, "iv": 0.25, "dte": 20,
                    })
                    option_positions.append({
                        "symbol": f"OPT-P-{put_strike}", "strike": put_strike,
                        "type": "put", "direction": -1, "lots": LOT_SIZE, "iv": 0.25, "dte": 20,
                    })

        # Delta动态对冲
        total_delta = 0.0
        for pos in option_positions:
            strike = pos["strike"]
            direction = pos["direction"]
            lots = pos["lots"]
            pos_type = pos["type"]
            moneyness = (spot - strike) / spot if pos_type == "call" else (strike - spot) / spot
            delta = direction * lots * (0.5 + 0.5 * np.sign(moneyness)) * np.exp(-abs(moneyness) * 3)
            total_delta += delta
        if abs(total_delta) > 0.5:
            hedge_lot = -int(total_delta)
            print(f"         >>> Delta对冲: 期货{'做多' if hedge_lot > 0 else '做空'} {abs(hedge_lot)}手")

        # 清理到期头寸
        for pos in option_positions[:]:
            pos["dte"] -= 1
            if pos["dte"] <= DTE_MIN:
                print(f"         >>> 清理: {pos['type']} K={pos['strike']} (到期)")
                option_positions.remove(pos)

    api.close()

if __name__ == "__main__":
    main()
