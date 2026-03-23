#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略34 - 期权希腊值风险平价组合策略（Options Greeks Risk Parity Portfolio Strategy）
======================================================================================

原理：
    构建基于Greeks（Delta、Gamma、Vega、Theta）的期权风险平价组合，
    实现跨品种、跨策略的等风险权重配置。

    【三个期权组合】
    组合A（Straddle）：买入ATM Call + ATM Put → 大Gamma + 大Vega -Theta
    组合B（Vertical Spread）：买入OTM Call + 卖出ATM Call → 小Vega + 正Theta
    组合C（Iron Condor）：卖出宽跨 + 保护翅膀 → 负Gamma + 收集Theta

    【风险平价配置】
    各组合在Greeks维度（Gamma + Vega）上的风险贡献相等
    权重 = 1 / 各组合Greeks总量，归一化
    目标：组合整体Delta ≈ 0, Vega ≈ 0

    【每日再平衡】
    任一Greeks超过目标阈值时触发再平衡
    Gamma预警（防止Gamma绞杀）

参数：
    标的：510050.SH（50ETF）
    Greeks目标：Delta≈0, Vega≈0
    再平衡阈值：任一Greeks超过目标20%触发
    最大风险敞口：净值50%
    Gamma预警阈值：净值30%
作者：setherffw / tqsdk-options
"""

from tqsdk import TqApi, TqAuth, TqSim, TargetPosTask
import numpy as np
import pandas as pd
import time

# ============ 参数配置 ============
UNDERLYING = "510050.SH"
EXPIRY = "2026-03"
S_REF = 3.0
K_ATM = 3.00
K_OTM_CALL = 3.10
K_IRON_SC_HIGH = 3.15
K_IRON_LC = 3.20
K_IRON_SP_LOW = 2.85
K_IRON_LP_LOW = 2.80

LEG_A_LC = f"{UNDERLYING}-{EXPIRY}-C-{K_ATM:.2f}"
LEG_A_LP = f"{UNDERLYING}-{EXPIRY}-P-{K_ATM:.2f}"
LEG_B_LC = f"{UNDERLYING}-{EXPIRY}-C-{K_OTM_CALL:.2f}"
LEG_B_SC = f"{UNDERLYING}-{EXPIRY}-C-{K_ATM:.2f}"
LEG_C_LC = f"{UNDERLYING}-{EXPIRY}-C-{K_IRON_LC:.2f}"
LEG_C_SC = f"{UNDERLYING}-{EXPIRY}-C-{K_IRON_SC_HIGH:.2f}"
LEG_C_LP = f"{UNDERLYING}-{EXPIRY}-P-{K_IRON_LP_LOW:.2f}"
LEG_C_SP = f"{UNDERLYING}-{EXPIRY}-P-{K_IRON_SP_LOW:.2f}"

KLINE_DUR = 60 * 30
REBALANCE_INTERVAL = 6
MAX_RISK = 0.50
GAMMA_ALERT = 0.30
VEGA_ALERT = 0.20
CAPITAL = 100000
MULT = 10000
# ==================================


def bs_greeks(S, K, T, r, quote, is_call, iv_override=None):
    from math import sqrt, log, exp, erf
    if T <= 0 or quote <= 0:
        return {"iv": 0.3, "delta": 0.5 if is_call else -0.5, "gamma": 0.0, "vega": 0.0, "theta": 0.0}
    intrinsic = max(S - K, 0) if is_call else max(K - S, 0)
    tv = max(quote - intrinsic, 0.001)
    iv = iv_override if iv_override else min(max(tv / (S * sqrt(max(T, 0.0001)) * 0.4 + 0.01), 0.05), 2.0)
    d1 = (log(S / K) + (r + 0.5 * iv ** 2) * T) / (iv * sqrt(max(T, 0.0001)) + 0.0001)
    d2 = d1 - iv * sqrt(max(T, 0.0001))
    pdf = exp(-0.5 * d1 ** 2) / sqrt(2 * 3.14159)
    cdf_d1 = 0.5 + 0.5 * erf(d1 / sqrt(2))
    delta = cdf_d1 if is_call else cdf_d1 - 1
    gamma = pdf / (S * iv * sqrt(max(T, 0.0001)) + 0.0001)
    vega = S * pdf * sqrt(max(T, 0.0001)) / 100
    theta = (-S * pdf * iv / (2 * sqrt(max(T, 0.0001))) - r * K * exp(-r * T) * (cdf_d1 if is_call else (1 - cdf_d1))) / 365
    return {"iv": iv, "delta": delta, "gamma": gamma, "vega": vega, "theta": theta}


def main():
    api = TqApi(auth=TqAuth("13556817485", "asd159753"))
    print("=" * 60)
    print("策略34：期权希腊值风险平价组合策略")
    print("=" * 60)

    legs = {
        LEG_A_LC: True, LEG_A_LP: False,
        LEG_B_LC: True, LEG_B_SC: True,
        LEG_C_LC: True, LEG_C_SC: True,
        LEG_C_LP: False, LEG_C_SP: False,
    }
    serials = {}
    for leg in legs:
        serials[leg] = api.get_tick_serial(leg)
        print(f"  订阅：{leg}")

    underlying_serial = api.get_tick_serial(UNDERLYING)
    print(f"  订阅：{UNDERLYING}")
    print("\n等待数据加载...")
    time.sleep(5)

    period_counter = 0
    last_rebalance = None

    print("\n策略34启动，监控Greeks风险平价...")

    with api.register_update_notify():
        while True:
            api.wait_update()
            now = api.get_trading_time()
            if now is None:
                continue
            period_counter += 1

            if len(underlying_serial) < 10:
                continue

            S = underlying_serial["close"].iloc[-1]
            T = 20 / 252

            quotes = {}
            greeks = {}
            ready = True
            for leg, is_call in legs.items():
                serial = serials[leg]
                if len(serial) < 2:
                    ready = False
                    break
                quote = serial["close"].iloc[-1]
                K = float(leg.split("-")[-1])
                g = bs_greeks(S, K, T, 0.03, quote, is_call)
                quotes[leg] = quote
                greeks[leg] = g

            if not ready or len(greeks) < len(legs):
                continue

            # 组合A: ATM Straddle
            gA = {k: greeks[LEG_A_LC][k] + greeks[LEG_A_LP][k] for k in ["delta", "gamma", "vega", "theta"]}
            # 组合B: Call Spread
            gB = {k: greeks[LEG_B_LC][k] - greeks[LEG_B_SC][k] for k in ["delta", "gamma", "vega", "theta"]}
            # 组合C: Iron Condor
            gC = {k: greeks[LEG_C_LC][k] - greeks[LEG_C_SC][k] + greeks[LEG_C_LP][k] - greeks[LEG_C_SP][k] for k in ["delta", "gamma", "vega", "theta"]}

            total = {k: gA[k] + gB[k] + gC[k] for k in ["delta", "gamma", "vega", "theta"]}

            delta_exp = abs(total["delta"]) * S * MULT
            gamma_exp = abs(total["gamma"]) * S * MULT
            vega_exp = abs(total["vega"]) * S * MULT
            risk_ratio = max(delta_exp / (CAPITAL * 0.5), gamma_exp / (CAPITAL * GAMMA_ALERT), vega_exp / (CAPITAL * VEGA_ALERT))

            if period_counter % REBALANCE_INTERVAL == 0:
                print(f"\n{'=' * 55}")
                print(f"【Greeks再平衡检查】{now}")
                print(f"  组合A(Straddle): Δ={gA['delta']:.4f}, Γ={gA['gamma']:.6f}, ν={gA['vega']:.4f}, Θ={gA['theta']:.4f}")
                print(f"  组合B(Spread):   Δ={gB['delta']:.4f}, Γ={gB['gamma']:.6f}, ν={gB['vega']:.4f}, Θ={gB['theta']:.4f}")
                print(f"  组合C(IronCond): Δ={gC['delta']:.4f}, Γ={gC['gamma']:.6f}, ν={gC['vega']:.4f}, Θ={gC['theta']:.4f}")
                print(f"  总Greeks:        Δ={total['delta']:.4f}, Γ={total['gamma']:.6f}, ν={total['vega']:.4f}, Θ={total['theta']:.4f}")
                print(f"  风险暴露: Δ={delta_exp:.0f}, Γ={gamma_exp:.0f}, ν={vega_exp:.0f}, 风险比例={risk_ratio:.2%}")

                # 风险平价权重
                total_greeks_exp = (abs(gA["gamma"]) + abs(gA["vega"]) + abs(gB["gamma"]) + abs(gB["vega"]) + abs(gC["gamma"]) + abs(gC["vega"]))
                if total_greeks_exp > 0:
                    wA = (abs(gA["gamma"]) + abs(gA["vega"])) / total_greeks_exp
                    wB = (abs(gB["gamma"]) + abs(gB["vega"])) / total_greeks_exp
                    wC = (abs(gC["gamma"]) + abs(gC["vega"])) / total_greeks_exp
                    print(f"  风险平价权重: A={wA:.2%}, B={wB:.2%}, C={wC:.2%}")

                if gamma_exp > CAPITAL * GAMMA_ALERT:
                    print(f"  ⚠️ Gamma预警！暴露={gamma_exp:.0f} > 阈值={CAPITAL*GAMMA_ALERT:.0f}")

                if abs(delta_exp) > CAPITAL * 0.20:
                    hedge = int(-total["delta"] * MULT / 100) * 100
                    print(f"  Delta对冲信号: {'买入' if hedge < 0 else '卖出'} {abs(hedge)}股ETF")

                print(f"{'=' * 55}")
                last_rebalance = now

            if period_counter % 20 == 1:
                print(f"📊 {now}: S={S:.3f}, Δ={total['delta']:.4f}, Γ={total['gamma']:.6f}, ν={total['vega']:.4f}, Θ={total['theta']:.4f}, 风险={risk_ratio:.1%}")


if __name__ == "__main__":
    main()
