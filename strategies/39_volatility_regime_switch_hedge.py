#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
策略39：期权波动率状态切换对冲策略
基于市场波动率状态（HIGH_vol / LOW_vol / SPIKE）自动切换对冲模式
在低波动率环境使用卖出期权策略（收Theta）
在高波动率环境使用买入期权策略（趋势跟随）
在波动率尖峰时快速平仓或反向对冲
"""

import numpy as np
import pandas as pd
from tqsdk import TqApi, TqAuth, TqOption, TargetPosTask

# ========== 策略参数 ==========
UNDERLYING = "SHFE.rb2505"           # 标的合约
INIT_PORTFOLIO = 2000000

# 波动率状态参数
VOL_HISTORY_WINDOW = 30              # 历史窗口（计算长期波动率均值）
VOL_SPIKE_THRESHOLD = 2.0             # 波动率尖峰倍数（超过均值的N倍判定为SPIKE）
VOL_LOW_THRESHOLD = 0.7              # 低波动率阈值（相对历史均值）
VOL_HIGH_THRESHOLD = 1.3             # 高波动率阈值

# 策略模式
MODE_LOW_VOL = "sell_vega"          # 低波动率模式：卖出期权收Theta
MODE_HIGH_VOL = "buy_vega"          # 高波动率模式：买入期权做多波动率
MODE_SPIKE = "close_or_hedge"       # 波动率尖峰模式：快速平仓或对冲
MODE_NEUTRAL = "wait"               # 中性模式：观望

# 希腊值风控
MAX_GREEKS = {
    "delta": 0.5,                   # 最大Delta暴露（占总资金比例）
    "gamma": 0.3,                   # 最大Gamma暴露
    "vega": 0.4,                    # 最大Vega暴露（对应IV变化1%）
    "theta": -1000,                 # 最小Theta收入（元/日）
}

# ========== 波动率状态检测 ==========
def detect_vol_regime(vol_history, current_vol):
    """检测当前波动率状态"""
    if len(vol_history) < VOL_HISTORY_WINDOW:
        return MODE_NEUTRAL

    recent_vols = list(vol_history)[-VOL_HISTORY_WINDOW:]
    mean_vol = np.mean(recent_vols)

    if current_vol > mean_vol * VOL_SPIKE_THRESHOLD:
        return MODE_SPIKE
    elif current_vol < mean_vol * VOL_LOW_THRESHOLD:
        return MODE_LOW_VOL
    elif current_vol > mean_vol * VOL_HIGH_THRESHOLD:
        return MODE_HIGH_VOL
    else:
        return MODE_NEUTRAL

def calc_portfolio_greeks(positions, option_data):
    """计算组合希腊值（简化版）"""
    total_delta = 0.0
    total_gamma = 0.0
    total_vega = 0.0
    total_theta = 0.0

    for pos in positions:
        option_sym = pos["symbol"]
        lot = pos["lots"]
        direction = pos["direction"]  # 1=long, -1=short

        # 简化希腊值估算
        iv = option_data.get(option_sym, {}).get("iv", 0.20)
        spot = option_data.get(option_sym, {}).get("spot", 4000)
        dte = option_data.get(option_sym, {}).get("dte", 30)

        # 简化Greeks（Black-Scholes近似）
        delta = direction * lot * 0.5 * (1 if "C" in option_sym else 0)
        gamma = direction * lot * 0.01 / (spot * 0.01)
        vega = direction * lot * iv * 0.01 * dte / 365
        theta = direction * lot * -0.5 * iv * iv / np.sqrt(dte / 365)

        total_delta += delta
        total_gamma += gamma
        total_vega += vega
        total_theta += theta

    return {
        "delta": total_delta,
        "gamma": total_gamma,
        "vega": total_vega,
        "theta": total_theta,
    }

# ========== 策略主体 ==========
def main():
    api = TqApi(auth=TqAuth("auto", "auto"))
    target_pos = TargetPosTask(api)

    print(f"[策略39] 波动率状态切换对冲策略启动 | 标的: {UNDERLYING}")

    underlying_quote = api.get_quote(UNDERLYING)
    spot_price = underlying_quote.last_price

    # 初始化K线（用K线数据估算波动率）
    kline_daily = api.get_kline_serial(UNDERLYING, 86400, data_length=100)
    kline_hourly = api.get_kline_serial(UNDERLYING, 3600, data_length=200)

    print(f"[策略39] ATM执行价: {spot_price:.2f}")

    # 历史波动率记录
    hv_history = []  # 历史波动率序列
    current_mode = MODE_NEUTRAL
    positions = []

    day_count = 0

    while True:
        api.wait_update()
        day_count += 1

        # 每天计算一次波动率状态
        if day_count % 1 != 0:
            continue

        spot = underlying_quote.last_price
        if spot <= 0:
            continue

        # 计算历史波动率（基于日收益率）
        if len(kline_daily.close) < VOL_HISTORY_WINDOW:
            continue

        returns = np.diff(np.log(kline_daily.close))
        if len(returns) < VOL_HISTORY_WINDOW:
            continue

        # 短期波动率（20日）
        hv_20d = np.std(returns[-20:]) * np.sqrt(252) if len(returns) >= 20 else 0.0
        hv_history.append(hv_20d)

        current_vol = hv_20d
        new_mode = detect_vol_regime(hv_history, current_vol)

        if new_mode != current_mode:
            print(f"\n[策略39] 波动率状态切换: {current_mode} → {new_mode}")
            print(f"         当前HV={current_vol:.4f} | 历史均值={np.mean(hv_history[-VOL_HISTORY_WINDOW:]):.4f}")
            current_mode = new_mode

        # 波动率尖峰处理
        if current_mode == MODE_SPIKE:
            print(f"[策略39] 波动率尖峰！快速平仓所有期权头寸")
            for pos in positions:
                target_pos.set_target_pos(pos["symbol"], 0)
            positions = []

        # 低波动率模式：卖出期权
        elif current_mode == MODE_LOW_VOL:
            print(f"[策略39] 低波动率模式 | 卖方策略")
            # ATM卖出看跌期权（收取Theta）
            atm_strike = round(spot / 10) * 10
            put_sym = f"{UNDERLYING.split('.')[0]}.{UNDERLYING.split('.')[1]}PE{atm_strike // 10}"
            # 检查是否已有头寸
            existing = [p for p in positions if p["symbol"] == put_sym]
            if not existing:
                # 估算保证金，控制仓位
                greeks = calc_portfolio_greeks(positions, {})
                remaining_vega = MAX_GREEKS["vega"] - abs(greeks["vega"])
                if remaining_vega > 0:
                    lot = max(1, int(remaining_vega * 100))  # 简化
                    print(f"         >>> 卖出PUT {put_sym} {lot}手 (ATM={atm_strike})")
                    # 实际下单需根据TqOption数据
                    positions.append({"symbol": put_sym, "lots": lot, "direction": -1})

        # 高波动率模式：买入期权
        elif current_mode == MODE_HIGH_VOL:
            print(f"[策略39] 高波动率模式 | 买方策略（趋势跟随）")
            # 买入虚值Call（突破行情）
            otm_strike = round(spot * 1.03 / 10) * 10
            call_sym = f"{UNDERLYING.split('.')[0]}.{UNDERLYING.split('.')[1]}CE{otm_strike // 10}"
            existing = [p for p in positions if p["symbol"] == call_sym]
            if not existing:
                greeks = calc_portfolio_greeks(positions, {})
                remaining_gamma = MAX_GREEKS["gamma"] - abs(greeks["gamma"])
                if remaining_gamma > 0:
                    lot = max(1, int(remaining_gamma * 100))
                    print(f"         >>> 买入CALL {call_sym} {lot}手 (OTM={otm_strike})")
                    positions.append({"symbol": call_sym, "lots": lot, "direction": 1})

        # 希腊值风控
        greeks = calc_portfolio_greeks(positions, {})
        print(f"[策略39] 希腊值 | Delta={greeks['delta']:.2f} "
              f"Gamma={greeks['gamma']:.2f} Vega={greeks['vega']:.2f} Theta={greeks['theta']:.2f}")

        # 超限风控平仓
        if abs(greeks["delta"]) > MAX_GREEKS["delta"] * INIT_PORTFOLIO / spot / 10:
            print(f"[策略39] Delta超限！执行动态对冲")
            # 对冲标的期货
            hedge_lot = int(greeks["delta"])
            underlying_sym = UNDERLYING
            target_pos.set_target_pos(underlying_sym, hedge_lot)

    api.close()

if __name__ == "__main__":
    main()
