#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
策略38：期权希腊字母风险平价组合策略
基于波动率、delta、gamma、theta、vega的期权组合风险平价配置
实现各风险因子的等权重暴露，适用于期权组合对冲与增强收益
"""

import numpy as np
import pandas as pd
from tqsdk import TqApi, TqAuth
from collections import defaultdict

UNDERLYING = "SHFE.rb2505"
INIT_PORTFOLIO = 2000000
TARGET_RISK_BUDGET = 100000
RISK_FACTORS = ["delta", "gamma", "theta", "vega"]
RISK_WEIGHTS = [0.25, 0.25, 0.25, 0.25]
DELTA_HEDGE_BAND = 0.30
GAMMA_ALERT = 5000
VEGA_EXPOSURE_LIMIT = 50000

def estimate_delta(S, K, T, r, sigma, option_type="call"):
    if T <= 0:
        return 1.0 if option_type == "call" and S >= K else 0.0
    from math import sqrt, log, exp, erf
    d1 = (log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    if option_type == "call":
        delta = 0.5 + 0.5 * erf(d1 / sqrt(2))
    else:
        delta = 0.5 - 0.5 * erf(d1 / sqrt(2))
    return delta

def estimate_gamma(S, K, T, r, sigma):
    if T <= 0 or S <= 0 or sigma <= 0:
        return 0.0
    from math import sqrt, log, exp, erf
    d1 = (log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    pdf_d1 = exp(-d1**2 / 2) / sqrt(2 * 3.14159265)
    return pdf_d1 / (S * sigma * sqrt(T))

def estimate_theta(S, K, T, r, sigma, option_type="call"):
    if T <= 0:
        return 0.0
    from math import sqrt, log, exp, erf
    d1 = (log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    pdf_d1 = exp(-d1**2 / 2) / sqrt(2 * 3.14159265)
    term1 = -S * pdf_d1 * sigma / (2 * sqrt(T))
    if option_type == "call":
        term2 = -r * K * exp(-r * T) * (0.5 + 0.5 * erf(d2 / sqrt(2)))
    else:
        term2 = r * K * exp(-r * T) * (0.5 - 0.5 * erf(d2 / sqrt(2)))
    return (term1 + term2) / 365

def estimate_vega(S, K, T, r, sigma, option_type="call"):
    if T <= 0 or sigma <= 0:
        return 0.0
    from math import sqrt, log, exp, erf
    d1 = (log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    pdf_d1 = exp(-d1**2 / 2) / sqrt(2 * 3.14159265)
    return S * sqrt(T) * pdf_d1 / 100

def calculate_greeks_for_strike(S, K, T, r, sigma, position_size, option_type="call"):
    delta = estimate_delta(S, K, T, r, sigma, option_type)
    gamma = estimate_gamma(S, K, T, r, sigma)
    theta = estimate_theta(S, K, T, r, sigma, option_type)
    vega = estimate_vega(S, K, T, r, sigma, option_type)
    return {
        "delta": delta * position_size * S * 0.01,
        "gamma": gamma * position_size * S**2 * 0.0001,
        "theta": theta * position_size,
        "vega": vega * position_size * sigma * 0.01,
    }

def risk_parity_rebalance(current_greeks, target_total_risk):
    greeks_total = {f: abs(current_greeks[f]) + 1e-8 for f in RISK_FACTORS}
    risk_per_factor = target_total_risk / 4
    adjustments = {}
    for factor in RISK_FACTORS:
        adjustments[factor] = risk_per_factor / greeks_total[factor]
    return adjustments, greeks_total

def main():
    api = TqApi(auth=TqAuth("auto", "auto"))
    print(f"[策略38] 期权希腊字母风险平价组合策略启动 | 标的: {UNDERLYING}")
    underlying_quote = api.get_quote(UNDERLYING)

    option_universe = [
        (3800, 30, 0.22, "put", 1, 80),
        (3900, 30, 0.21, "put", -2, 120),
        (4000, 30, 0.20, "call", 2, 100),
        (4100, 30, 0.21, "call", -1, 80),
        (3850, 60, 0.23, "put", 1, 120),
        (4050, 60, 0.22, "call", -1, 110),
    ]

    spot = underlying_quote.last_price
    T = 30 / 365
    r = 0.03
    print(f"[策略38] Spot={spot:.2f} | 初始组合: {len(option_universe)} 个期权腿")

    while True:
        api.wait_update()
        spot = underlying_quote.last_price
        if spot <= 0 or np.isnan(spot):
            continue

        portfolio_greeks = defaultdict(float)
        for strike, expiry, iv, opt_type, pos_size, _ in option_universe:
            T_eff = max(expiry / 365, 1/365)
            greeks = calculate_greeks_for_strike(spot, strike, T_eff, r, iv, pos_size, opt_type)
            for factor, value in greeks.items():
                portfolio_greeks[factor] += value

        print(f"\n[策略38] ===== Greeks汇总 =====")
        for factor in RISK_FACTORS:
            print(f"  {factor.capitalize():6s}: {portfolio_greeks[factor]:>12.2f}")

        if abs(portfolio_greeks["delta"]) > spot * DELTA_HEDGE_BAND:
            hedge_lots = int(portfolio_greeks["delta"] / (spot * 0.01))
            print(f"  >>> Delta对冲信号: 需要{'卖出' if hedge_lots > 0 else '买入'} {abs(hedge_lots)} 手标的")

        if abs(portfolio_greeks["gamma"]) > GAMMA_ALERT:
            print(f"  >>> Gamma预警: 暴露过大，考虑减少期权头寸")

        if abs(portfolio_greeks["vega"]) > VEGA_EXPOSURE_LIMIT:
            print(f"  >>> Vega暴露超限: 当前{portfolio_greeks['vega']:.0f} > 限额{VEGA_EXPOSURE_LIMIT}")

        print(f"  >>> Theta日收益: {portfolio_greeks['theta']:.2f} 元/天")

        adj, total_risk = risk_parity_rebalance(portfolio_greeks, TARGET_RISK_BUDGET)
        print(f"\n[策略38] ===== 风险平价调整建议 =====")
        for factor in RISK_FACTORS:
            print(f"  {factor.capitalize():6s}: 当前={total_risk[factor]:.2f} | 目标={TARGET_RISK_BUDGET/4:.2f} | 调整系数={adj[factor]:.3f}")

        import time
        time.sleep(86400)

    api.close()

if __name__ == "__main__":
    main()
