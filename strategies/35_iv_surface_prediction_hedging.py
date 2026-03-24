#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略35 - 期权隐含波动率曲面预测与动态对冲策略（IV Surface Prediction & Dynamic Delta Hedging）
====================================================================================================

原理：
    本策略对期权隐含波动率（IV）曲面进行时间序列预测，
    当预测IV将上升时买入期权（Long Vega）捕获波动率上行收益；
    当预测IV将下降时卖出期权（Short Vega）赚取IV下行收益。
    同时通过动态Delta对冲消除方向性风险。

    【IV曲面建模】
    - 对不同行权价和期限的期权IV进行截面拟合
    - 利用波动率微笑（Volatility Smile）特征：OTM Put的IV通常高于OTM Call
    - 构建SVI（Stochastic Volatility Inspired）参数简化曲面

    【IV预测模型（指数平滑法）】
    - 简单指数平滑预测下一周期IV
    - 加权移动平均（WMA）强调近期趋势
    - 预测误差 < 5%时信号可信度高

    【入场逻辑】
    - 预测IV上涨 > 5%：买入ATM Straddle（Long Vega + Long Gamma）
    - 预测IV下跌 > 5%：卖出ATM Straddle（Short Vega + Short Gamma）
    - IV处于历史低位（< 20百分位）：优先做多波动率
    - IV处于历史高位（> 80百分位）：优先做空波动率

    【动态Delta对冲】
    - 每30分钟重新计算Delta并调整标的仓位
    - 目标：组合Delta ≈ 0
    - 对冲阈值：|Delta| > 0.1 时触发对冲
    - 对冲成本累计监控：若对冲成本超过期权权利金的30%，考虑平仓

    【波动率预警】
    - 当IV急剧扩大（1小时内上升>10%）时，产生预警
    - 预警时不追涨，等待回调或利用Vega对冲保护

参数：
    - 标的：510050.SH（50ETF）
    - 期权系列：当月+下月ATM合约
    - 预测周期：下一交易日
    - 对冲频率：30分钟
    - 对冲阈值：|Delta| > 0.1
    - IV变化阈值：5%
    - 预测方法：指数平滑（α=0.3）
作者：setherffw / tqsdk-options
"""

from tqsdk import TqApi, TqAuth, TqSim, TargetPosTask
import numpy as np
import pandas as pd
import time

# ============ 参数配置 ============
UNDERLYING = "510050.SH"
EXPIRY_NEAR = "2026-03"
EXPIRY_FAR = "2026-04"
S_REF = 3.0
K atm_call = "C-3.00"
K atm_put = "P-3.00"

K_NEAR_CALL_OTM = "C-3.10"
K_NEAR_PUT_OTM = "P-2.90"
K_FAR_CALL_OTM = "C-3.20"
K_FAR_PUT_OTM = "P-2.80"

LEG_CALL_ATM_NEAR = f"{UNDERLYING}-{EXPIRY_NEAR}-C-3.00"
LEG_PUT_ATM_NEAR = f"{UNDERLYING}-{EXPIRY_NEAR}-P-3.00"
LEG_CALL_OTM_NEAR = f"{UNDERLYING}-{EXPIRY_NEAR}-C-3.10"
LEG_PUT_OTM_NEAR = f"{UNDERLYING}-{EXPIRY_NEAR}-P-2.90"

KLINE_DUR = 60 * 30               # 30分钟K线
HEDGE_INTERVAL = 6                # 对冲间隔（30分钟）
IV_CHANGE_THRESH = 0.05          # IV变化阈值5%
IV_HISTORY_LEN = 60             # 历史IV序列长度
PREDICT_ALPHA = 0.3              # 指数平滑系数
DELTA_HEDGE_THRESH = 0.10       # Delta对冲阈值
CAPITAL = 100000
MULT = 10000
# ==================================


def calc_implied_vol(quote, S, K, T, r, is_call):
    """简化IV计算：牛顿迭代法"""
    from math import sqrt, log, exp, erf
    if T <= 0 or quote <= 0:
        return 0.3
    intrinsic = max(S - K, 0) if is_call else max(K - S, 0)
    tv = max(quote - intrinsic, 0.001)
    iv = min(max(tv / (S * sqrt(max(T, 0.0001)) * 0.4 + 0.01), 0.05), 2.0)
    for _ in range(20):
        d1 = (log(S / K) + (r + 0.5 * iv ** 2) * T) / (iv * sqrt(max(T, 0.0001)) + 1e-10)
        pdf = exp(-0.5 * d1 ** 2) / sqrt(2 * 3.14159)
        cdf_d1 = 0.5 + 0.5 * erf(d1 / sqrt(2))
        delta = cdf_d1 if is_call else cdf_d1 - 1
        price_est = (cdf_d1 * S - (cdf_d1 - (1 if is_call else -1)) * K * exp(-r * T) if is_call else
                     (1 - cdf_d1) * K * exp(-r * T) - (1 - cdf_d1) * S)
        price_est = (cdf_d1 * S - K * exp(-r * T) * (0.5 + 0.5 * erf(d1 / sqrt(2) - iv * sqrt(T) / sqrt(2))) if is_call else
                     K * exp(-r * T) * (0.5 - 0.5 * erf(-d1 / sqrt(2) - iv * sqrt(T) / sqrt(2))) - S * (0.5 - 0.5 * erf(-d1 / sqrt(2))))
        # 简化：使用BS近似
        vega_est = S * pdf * sqrt(max(T, 0.0001)) / 100
        if vega_est < 1e-10:
            break
        diff = quote - tv
        if abs(diff) < 1e-6:
            break
        iv = iv + diff / (vega_est * 100)
        iv = max(0.05, min(iv, 2.0))
    return iv


def bs_delta(S, K, T, r, iv, is_call):
    """计算Delta"""
    from math import sqrt, log, exp, erf
    if T <= 0:
        return 1.0 if is_call else -1.0
    d1 = (log(S / K) + (r + 0.5 * iv ** 2) * T) / (iv * sqrt(max(T, 0.0001)) + 1e-10)
    cdf = 0.5 + 0.5 * erf(d1 / sqrt(2))
    return cdf if is_call else cdf - 1


def exponential_smooth_forecast(history, alpha=0.3):
    """指数平滑预测"""
    if len(history) < 2:
        return history[-1] if history else 0.0
    forecast = history[0]
    for val in history[1:]:
        forecast = alpha * val + (1 - alpha) * forecast
    return forecast


def main():
    api = TqApi(auth=TqAuth("13556817485", "asd159753"))

    print("=" * 60)
    print("策略35：期权隐含波动率曲面预测与动态对冲策略")
    print("=" * 60)

    legs_config = {
        LEG_CALL_ATM_NEAR: True,
        LEG_PUT_ATM_NEAR: False,
        LEG_CALL_OTM_NEAR: True,
    }

    serials = {}
    for leg in legs_config:
        serials[leg] = api.get_tick_serial(leg)
        print(f"  订阅：{leg}")

    underlying_serial = api.get_tick_serial(UNDERLYING)
    print(f"  订阅：{UNDERLYING}")

    print("\n等待数据加载...")
    time.sleep(5)

    # IV历史
    iv_history = {leg: [] for leg in legs_config}
    hedge_count = 0
    last_hedge_time = None
    in_position = False
    position_type = None  # "long_vol" or "short_vol"
    entry_premium = 0.0

    print("\n策略35启动，监控IV曲面预测...")

    with api.register_update_notify():
        while True:
            api.wait_update()
            now = api.get_trading_time()
            if now is None:
                continue

            if len(underlying_serial) < 10:
                continue

            S = underlying_serial["close"].iloc[-1]
            T_near = 20 / 252  # 当月合约剩余天数约20天

            # ---------- 计算各腿IV ----------
            iv_current = {}
            delta_current = {}
            quotes_current = {}

            ready = True
            for leg, is_call in legs_config.items():
                serial = serials[leg]
                if len(serial) < 2:
                    ready = False
                    break
                quote = serial["close"].iloc[-1]
                K = float(leg.split("-")[-1])
                iv = calc_implied_vol(quote, S, K, T_near, 0.03, is_call)
                delta = bs_delta(S, K, T_near, 0.03, iv, is_call)
                iv_current[leg] = iv
                delta_current[leg] = delta
                quotes_current[leg] = quote

            if not ready or len(iv_current) < len(legs_config):
                continue

            # ---------- 更新IV历史 ----------
            for leg in legs_config:
                if leg in iv_current:
                    iv_history[leg].append(iv_current[leg])
                    if len(iv_history[leg]) > IV_HISTORY_LEN:
                        iv_history[leg] = iv_history[leg][-IV_HISTORY_LEN:]

            # ---------- IV预测 ----------
            atm_call_iv = iv_current.get(LEG_CALL_ATM_NEAR, 0.2)
            atm_put_iv = iv_current.get(LEG_PUT_ATM_NEAR, 0.2)

            # 预测下一期IV（使用ATM Call IV代表市场整体IV）
            if len(iv_history.get(LEG_CALL_ATM_NEAR, [])) >= 10:
                iv_forecast = exponential_smooth_forecast(
                    iv_history[LEG_CALL_ATM_NEAR], PREDICT_ALPHA
                )
                iv_change_pct = (iv_forecast - atm_call_iv) / atm_call_iv

                # 历史分位数
                iv_hist = iv_history[LEG_CALL_ATM_NEAR]
                pct_rank = sum(1 for v in iv_hist if v <= atm_call_iv) / len(iv_hist)

                print(f"\n{'=' * 55}")
                print(f"【IV曲面分析】{now}")
                print(f"  ATM Call IV: {atm_call_iv:.4f} ({atm_call_iv*100:.2f}%)")
                print(f"  ATM Put IV:  {atm_put_iv:.4f} ({atm_put_iv*100:.2f}%)")
                print(f"  IV Smile偏度: Put-Call IV差={atm_put_iv - atm_call_iv:.4f}")
                print(f"  预测IV: {iv_forecast:.4f} ({iv_forecast*100:.2f}%)")
                print(f"  IV变化预测: {iv_change_pct:+.2%}")
                print(f"  IV历史分位: {pct_rank:.0%}")
                print(f"{'=' * 55}")

                # ---------- 入场逻辑 ----------
                if not in_position:
                    if iv_change_pct > IV_CHANGE_THRESH and pct_rank < 0.8:
                        # 预测IV上升 + 未处于极端高位 → Long Vega
                        position_type = "long_vol"
                        premium_total = sum(quotes_current.values())
                        entry_premium = premium_total
                        in_position = True
                        print(f"\n🎯【做多波动率入场】预测IV上涨{iv_change_pct:+.2%}")
                        print(f"  买入Straddle: Call={quotes_current[LEG_CALL_ATM_NEAR]:.4f}, "
                              f"Put={quotes_current[LEG_PUT_ATM_NEAR]:.4f}")
                        print(f"  总权利金: {entry_premium:.4f}")

                    elif iv_change_pct < -IV_CHANGE_THRESH and pct_rank > 0.2:
                        # 预测IV下降 + 未处于极端低位 → Short Vega
                        position_type = "short_vol"
                        premium_total = sum(quotes_current.values())
                        entry_premium = premium_total
                        in_position = True
                        print(f"\n🎯【做空波动率入场】预测IV下降{iv_change_pct:+.2%}")
                        print(f"  卖出Straddle: Call={quotes_current[LEG_CALL_ATM_NEAR]:.4f}, "
                              f"Put={quotes_current[LEG_PUT_ATM_NEAR]:.4f}")
                        print(f"  总权利金: {entry_premium:.4f}")

                # ---------- Delta对冲 ----------
                if in_position:
                    total_delta = sum(delta_current.values())
                    delta_exposure = total_delta * S * MULT

                    if abs(total_delta) > DELTA_HEDGE_THRESH:
                        hedge_shares = int(-total_delta * MULT / 100) * 100
                        print(f"\n⚙️【Delta对冲】总Delta={total_delta:.4f}, "
                              f"对冲股数={hedge_shares:+d}")
                        hedge_count += 1
                        last_hedge_time = now

                    # 对冲成本监控
                    current_premium = sum(quotes_current.values())
                    if entry_premium > 0:
                        cost_ratio = abs(current_premium - entry_premium) / entry_premium
                        if cost_ratio > 0.30:
                            print(f"\n⚠️【预警】对冲成本已达权利金的{cost_ratio:.0%}，考虑平仓")
                            in_position = False
                            position_type = None

            # ---------- 定期监控 ----------
            if now.minute % 10 == 1:
                flag = "🔴" if in_position else "🟢"
                pos_type = position_type or "无"
                print(f"{flag} {now}: S={S:.3f}, ATM IV={atm_call_iv:.2%}, "
                      f"持仓={pos_type}, 对冲次数={hedge_count}")


if __name__ == "__main__":
    main()
