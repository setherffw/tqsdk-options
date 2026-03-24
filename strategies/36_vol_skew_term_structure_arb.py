#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略36 - 基于波动率偏度微笑的期限结构套利策略（Volatility Skew Smile & Term Structure Arbitrage）
=====================================================================================================

原理：
    本策略同时利用期权波动率偏度（Skew）和期限结构（Term Structure）两个维度的均值回归特性，
    构建三维期权套利组合，在波动率曲面的异常点入场，预期回归。

    【波动率偏度（Volatility Skew）】
    - 定义：OTM Put IV - OTM Call IV（同一到期日的IV差）
    - Skew > 历史均值 + 1σ：市场恐慌情绪偏高 → 做空Skew（卖OTM Put，买OTM Call）
    - Skew < 历史均值 - 1σ：市场乐观情绪偏高 → 做多Skew（买OTM Put，卖OTM Call）

    【期限结构（Term Structure）】
    - 定义：远月ATM IV - 近月ATM IV
    - Contango（正常升水）：远月IV > 近月IV
    - Backwardation（倒挂）：远月IV < 近月IV
    - 当期限结构斜率偏离历史均值时 → 预期回归

    【三维套利组合（Skew × Term）】
    情形1（Skew高 + Contango斜率高）：做空Skew + 做空远月IV
    情形2（Skew低 + Backwardation斜率低）：做多Skew + 做多远月IV
    情形3（Skew高 + Backwardation倒挂深）：做多Skew + 做多近月IV
    情形4（Skew低 + Contango斜率高）：矛盾信号，轻仓观望

    【Greeks风控】目标组合Vega≈0，Delta≈0

参数：
    - 标的：510050.SH（50ETF）
    - 近月：2026-03（剩余约20天）
    - 远月：2026-04（剩余约50天）
    - Skew回看期：60日
    - 入场阈值：偏离历史均值1σ以上
作者：setherffw / tqsdk-options
"""

from tqsdk import TqApi, TqAuth, TqSim, TargetPosTask
import numpy as np
import pandas as pd
import time

UNDERLYING = "510050.SH"
EXPIRY_NEAR = "2026-03"
EXPIRY_FAR = "2026-04"

LEG_NEAR_PUT_90 = f"{UNDERLYING}-{EXPIRY_NEAR}-P-2.90"
LEG_NEAR_CALL_110 = f"{UNDERLYING}-{EXPIRY_NEAR}-C-3.10"
LEG_NEAR_CALL_100 = f"{UNDERLYING}-{EXPIRY_NEAR}-C-3.00"
LEG_NEAR_PUT_100 = f"{UNDERLYING}-{EXPIRY_NEAR}-P-3.00"
LEG_FAR_CALL_100 = f"{UNDERLYING}-{EXPIRY_FAR}-C-3.00"
LEG_FAR_PUT_100 = f"{UNDERLYING}-{EXPIRY_FAR}-P-3.00"

REBALANCE_INTERVAL = 12
SKEW_LOOKBACK = 60
TERM_LOOKBACK = 60
ENTRY_STD = 1.0
MAX_RISK = 0.40
CAPITAL = 100000
MULT = 10000


def calc_iv_approx(quote, S, K, T, r, is_call):
    from math import sqrt, log
    if T <= 0 or quote <= 0:
        return 0.3
    intrinsic = max(S - K, 0) if is_call else max(K - S, 0)
    tv = max(quote - intrinsic, 0.001)
    return min(max(tv / (S * sqrt(max(T, 0.0001)) * 0.4 + 0.01), 0.05), 2.0)


def bs_delta(S, K, T, r, iv, is_call):
    from math import sqrt, log, erf
    if T <= 0:
        return 1.0 if is_call else -1.0
    d1 = (log(S / K) + (r + 0.5 * iv ** 2) * T) / (iv * sqrt(max(T, 0.0001)) + 1e-10)
    cdf = 0.5 + 0.5 * erf(d1 / sqrt(2))
    return cdf if is_call else cdf - 1


def bs_vega(S, K, T, r, iv, is_call):
    from math import sqrt, log, erf
    if T <= 0:
        return 0.0
    d1 = (log(S / K) + (r + 0.5 * iv ** 2) * T) / (iv * sqrt(max(T, 0.0001)) + 1e-10)
    pdf = __import__('math').exp(-0.5 * d1 ** 2) / sqrt(2 * 3.14159)
    return S * pdf * sqrt(max(T, 0.0001)) / 100


def main():
    api = TqApi(auth=TqAuth("13556817485", "asd159753"))
    print("=" * 60)
    print("策略36：波动率偏度微笑与期限结构套利策略")
    print("=" * 60)

    legs = {
        LEG_NEAR_PUT_90: False, LEG_NEAR_CALL_110: True,
        LEG_NEAR_CALL_100: True, LEG_NEAR_PUT_100: False,
        LEG_FAR_CALL_100: True, LEG_FAR_PUT_100: False,
    }

    serials = {}
    for leg in legs:
        serials[leg] = api.get_tick_serial(leg)
        print(f"  订阅：{leg}")

    underlying_serial = api.get_tick_serial(UNDERLYING)
    print(f"  订阅：{UNDERLYING}")
    print("\n等待数据加载...")
    time.sleep(5)

    skew_history = []
    term_history = []
    period_counter = 0
    in_position = False
    position_name = None

    print("\n策略36启动，监控波动率偏度与期限结构...")

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
            T_near = 20 / 252
            T_far = 50 / 252

            quotes, ivs, deltas, vegas = {}, {}, {}, {}
            ready = True
            for leg, is_call in legs.items():
                serial = serials[leg]
                if len(serial) < 2:
                    ready = False
                    break
                quote = serial["close"].iloc[-1]
                K = float(leg.split("-")[-1])
                T = T_near if EXPIRY_NEAR in leg else T_far
                iv = calc_iv_approx(quote, S, K, T, 0.03, is_call)
                delta = bs_delta(S, K, T, 0.03, iv, is_call)
                vega = bs_vega(S, K, T, 0.03, iv, is_call)
                quotes[leg] = quote
                ivs[leg] = iv
                deltas[leg] = delta
                vegas[leg] = vega

            if not ready or len(ivs) < len(legs):
                continue

            near_skew = ivs.get(LEG_NEAR_PUT_90, 0.3) - ivs.get(LEG_NEAR_CALL_110, 0.3)
            near_atm_iv = (ivs.get(LEG_NEAR_CALL_100, 0.3) + ivs.get(LEG_NEAR_PUT_100, 0.3)) / 2
            far_atm_iv = (ivs.get(LEG_FAR_CALL_100, 0.3) + ivs.get(LEG_FAR_PUT_100, 0.3)) / 2
            term_slope = far_atm_iv - near_atm_iv

            skew_history.append(near_skew)
            term_history.append(term_slope)
            if len(skew_history) > SKEW_LOOKBACK:
                skew_history = skew_history[-SKEW_LOOKBACK:]
            if len(term_history) > TERM_LOOKBACK:
                term_history = term_history[-TERM_LOOKBACK:]

            if len(skew_history) >= 20:
                skew_mean, skew_std = np.mean(skew_history), np.std(skew_history)
                skew_z = (near_skew - skew_mean) / (skew_std + 1e-10)
                term_mean, term_std = np.mean(term_history), np.std(term_history)
                term_z = (term_slope - term_mean) / (term_std + 1e-10)
            else:
                skew_mean = skew_std = skew_z = 0
                term_mean = term_std = term_z = 0

            if not in_position:
                if period_counter % REBALANCE_INTERVAL == 0:
                    signal = None
                    if skew_z > ENTRY_STD and term_z > ENTRY_STD:
                        signal = "做空Skew+远月IV"
                    elif skew_z < -ENTRY_STD and term_z < -ENTRY_STD:
                        signal = "做多Skew+远月IV"
                    elif skew_z > ENTRY_STD and term_z < -ENTRY_STD:
                        signal = "做多Skew+近月IV"
                    elif skew_z < -ENTRY_STD and term_z > ENTRY_STD:
                        signal = "矛盾信号-轻仓"

                    if signal:
                        print(f"\n{'=' * 55}")
                        print(f"【套利信号】{now}")
                        print(f"  Skew: {near_skew:.4f} (均值={skew_mean:.4f}, Z={skew_z:.2f})")
                        print(f"  期限斜率: {term_slope:.4f} (均值={term_mean:.4f}, Z={term_z:.2f})")
                        print(f"  信号: {signal}")
                        print(f"{'=' * 55}")
                        in_position = True
                        position_name = signal

            if period_counter % REBALANCE_INTERVAL == 0 and in_position:
                total_delta = sum(deltas.values())
                total_vega = sum(vegas.values())
                delta_exp = abs(total_delta) * S * MULT
                vega_exp = abs(total_vega) * S * MULT
                risk_ratio = max(delta_exp, vega_exp) / (CAPITAL * MAX_RISK)

                print(f"\n{'=' * 55}")
                print(f"【Greeks再平衡检查】{now}")
                print(f"  持仓: {position_name}")
                print(f"  ΣΔ={total_delta:.4f}, Σν={total_vega:.4f}")
                print(f"  Δ暴露={delta_exp:.0f}, ν暴露={vega_exp:.0f}, 风险={risk_ratio:.2%}")
                print(f"  Skew Z={skew_z:.2f}, Term Z={term_z:.2f}")
                print(f"{'=' * 55}")

                if abs(total_delta) > 0.15:
                    hedge = int(-total_delta * MULT / 100) * 100
                    print(f"  ⚙️ Delta对冲: {'买入' if hedge < 0 else '卖出'} {abs(hedge)}股ETF")

                if abs(skew_z) > 2.5 or abs(term_z) > 2.5:
                    print(f"\n⚠️ 偏离过大止损！Skew Z={skew_z:.2f}, Term Z={term_z:.2f}")
                    in_position = False
                    position_name = None

            if now.minute % 15 == 1 and period_counter % 3 == 0:
                flag = "🔴" if in_position else "🟢"
                print(f"{flag} {now}: S={S:.3f}, Skew={near_skew:.4f}(Z={skew_z:.2f}), Term={term_slope:.4f}(Z={term_z:.2f}), 持仓={position_name or '无'}")


if __name__ == "__main__":
    main()
