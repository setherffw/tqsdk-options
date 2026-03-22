#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略31 - 期权希腊值动态风控策略（Greeks-Based Dynamic Risk Management）
========================================================================

原理：
    期权组合的盈亏由四个"Greeks"共同决定：
    - Delta（方向）：标的价格变化对组合的影响
    - Gamma（加速度）：Delta对标的价格变化的敏感度
    - Vega（波动率敏感度）：隐含波动率变化对组合的影响
    - Theta（时间衰减）：每日时间价值流失

    本策略构建一个波动率价差组合（买低行权+卖高行权的Call Vertical Spread），
    并根据实时 Greeks 进行动态对冲和仓位调整：
    1. Delta对冲：根据当前组合Delta，动态调整标的仓位保持Delta中性
    2. Gamma预警：当|Gamma|超过阈值时，增加对冲频率
    3. Vega管理：监测组合Vega，当隐含波动率方向与持仓相反时提前平仓
    4. Theta收集：作为卖方，持续收获时间价值衰减

参数：
    - 标的：510050.SH（50ETF）
    - 组合：买低行权Call + 卖高行权Call（牛市垂直价差）
    - Delta对冲周期：每30分钟评估一次
    - Vega止损：IV单日变化 > 5% 时触发
    - Gamma预警阈值：> 0.05

适用行情：趋势明确但波动率适中，Theta套利空间充足
风险提示：Gamma风险（快到期时Delta剧变）、Vega风险（IV大幅波动）
作者：setherffw / tqsdk-options
"""

from tqsdk import TqApi, TqAuth, TqSim, TargetPosTask
import numpy as np
import pandas as pd
import time
from math import log, sqrt, exp

# ============ 参数配置 ============
UNDERLYING = "510050.SH"
CALL_BUY  = "510050.SH-2026-03-C-2.85"   # 买低行权价（实值）
CALL_SELL = "510050.SH-2026-03-C-3.00"  # 卖高行权价（虚值）

KLINE_DUR = 5 * 60                # K线周期：5分钟
HEDGE_INTERVAL = 1800               # 对冲间隔：30分钟
VEGA_STOP = 0.05                   # Vega止损：IV变化5%触发
GAMMA_THRESH = 0.05                # Gamma预警阈值
OPTION_LOT = 1                     # 期权持仓张数
FUTURE_LOT = 1                     # 对冲期货手数
# ==================================


def norm_cdf(x):
    """标准正态分布CDF近似"""
    return 0.5 * (1 + np.math.erf(x / sqrt(2)))


def norm_pdf(x):
    """标准正态分布PDF"""
    return exp(-0.5 * x * x) / sqrt(2 * np.pi)


def bsm_greeks(price, strike, T, iv, option_type="call", rate=0.03):
    """
    Black-Scholes-Merton Greeks计算
    T: 年化到期时间
    iv: 隐含波动率（年化）
    """
    if T <= 0 or iv <= 0 or price <= 0:
        return {"delta": 0, "gamma": 0, "vega": 0, "theta": 0}

    d1 = (log(price / strike) + (rate + 0.5 * iv ** 2) * T) / (iv * sqrt(T))
    d2 = d1 - iv * sqrt(T)

    if option_type == "call":
        delta = norm_cdf(d1)
    else:
        delta = norm_cdf(d1) - 1

    gamma = norm_pdf(d1) / (price * iv * sqrt(T))
    vega = price * norm_pdf(d1) * sqrt(T) / 100  # 每1%IV变化的影响

    if option_type == "call":
        theta = (-(price * norm_pdf(d1) * iv) / (2 * sqrt(T))
                 - rate * strike * exp(-rate * T) * norm_cdf(d2)) / 365
    else:
        theta = (-(price * norm_pdf(d1) * iv) / (2 * sqrt(T))
                 + rate * strike * exp(-rate * T) * norm_cdf(-d2)) / 365

    return {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta}


def main():
    api = TqApi(auth=TqAuth("13556817485", "asd159753"))

    print("=" * 60)
    print("策略31：期权希腊值动态风控策略")
    print("=" * 60)

    underlying_quote = api.get_quote(UNDERLYING)
    call_buy_quote = api.get_quote(CALL_BUY)
    call_sell_quote = api.get_quote(CALL_SELL)

    kl_underlying = api.get_kline_serial(UNDERLYING, KLINE_DUR)
    fut_pos = TargetPosTask(api, UNDERLYING)

    last_hedge_time = 0
    last_iv = None
    last_update = 0

    S = underlying_quote.last_price
    print(f"标的: {UNDERLYING}, 当前价格: {S:.3f}")
    print(f"买入期权: {CALL_BUY}, 卖出期权: {CALL_SELL}")
    print("开始监控Greeks风险...")

    expiry_days = 14  # 假设14天后到期

    while True:
        api.wait_update()
        now = time.time()

        # 价格变化时或到达对冲时间
        price_changed = (api.is_changing(underlying_quote, "last_price") or
                         api.is_changing(call_buy_quote, "last_price") or
                         api.is_changing(call_sell_quote, "last_price"))
        time_elapsed = (now - last_hedge_time) >= HEDGE_INTERVAL

        if not (price_changed or time_elapsed):
            continue

        S = underlying_quote.last_price
        iv_buy = call_buy_quote.implied_volatility if call_buy_quote.implied_volatility > 0 else 0.20
        iv_sell = call_sell_quote.implied_volatility if call_sell_quote.implied_volatility > 0 else 0.20

        if S <= 0 or iv_buy <= 0 or iv_sell <= 0:
            continue

        T = expiry_days / 365.0
        g_buy = bsm_greeks(S, 2.85, T, iv_buy, "call")
        g_sell = bsm_greeks(S, 3.00, T, iv_sell, "call")

        # 组合Greeks（买1张买方正，卖1张卖方负）
        total_delta = (g_buy["delta"] - g_sell["delta"]) * OPTION_LOT
        total_gamma = (g_buy["gamma"] - g_sell["gamma"]) * OPTION_LOT
        total_vega = (g_buy["vega"] - g_sell["vega"]) * OPTION_LOT
        total_theta = (g_buy["theta"] - g_sell["theta"]) * OPTION_LOT

        # Vega止损
        if last_iv is not None:
            iv_change = abs(iv_sell - last_iv) / (last_iv + 1e-10)
            if iv_change > VEGA_STOP:
                print(f"[警告] IV突变 {iv_change*100:.1f}%，检查Vega风险")
                if total_vega < 0 and iv_change > 0.10:
                    print(f"[止损] IV大幅上升，卖方Vega亏损严重，平仓！")
                    fut_pos.set_target_volume(0)
                    last_hedge_time = now
                    last_iv = iv_sell
                    continue

        last_iv = iv_sell

        # Gamma预警
        if abs(total_gamma) > GAMMA_THRESH:
            print(f"[预警] Gamma={total_gamma:.4f} 超过阈值 {GAMMA_THRESH}，增加对冲频率")

        # Delta对冲信号
        hedge_target = -int(round(total_delta * FUTURE_LOT))
        current_pos = fut_pos.target_pos

        if hedge_target != current_pos or (now - last_update) > 60:
            print(f"[{pd.Timestamp.now().strftime('%H:%M:%S')}] "
                  f"S={S:.3f} | Delta={total_delta:.3f} | Gamma={total_gamma:.4f} | "
                  f"Vega={total_vega:.3f} | Theta={total_theta:.3f} "
                  f"→ 对冲={hedge_target}")
            fut_pos.set_target_volume(hedge_target)
            last_hedge_time = now
            last_update = now

        time.sleep(5)


if __name__ == "__main__":
    main()
