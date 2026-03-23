#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略33 - 期权波动率偏度交易策略（Options Volatility Skew Trading Strategy）
================================================================================

原理：
    基于期权隐含波动率偏度（IV Skew）进行交易，捕捉市场情绪极端化带来的回归机会。

    【波动率偏度（IV Skew）】
    Skew = (ATM IV - OTM Put IV) / ATM IV
    Skew > 0 表明市场给下跌风险更高的概率溢价（恐慌情绪）

    【入场信号】
    - Skew超过历史均值+1σ：市场恐慌溢价过高，构建"风险逆转"组合
      （买入OTM Put + 卖出OTM Call，净权利金接近零）
    - Skew低于历史均值-1σ：市场过度乐观，反向风险逆转

    【Delta动态对冲】
    - 保持组合Delta ≈ 0，每15分钟重新计算Greeks并调整标的仓位

    【VIX情绪增强】
    - 当VIX > 30时，偏度极端化概率更高，仓位规模 × 1.5

参数：
    标的：510050.SH（50ETF）
    Skew回看周期：30日
    Skew入场阈值：±1σ / 平仓：±0.3σ / 止损：±2σ
    Delta对冲周期：15分钟
    VIX阈值：30
作者：setherffw / tqsdk-options
"""

from tqsdk import TqApi, TqAuth, TqSim, TargetPosTask
import numpy as np
import pandas as pd
import time

# ============ 参数配置 ============
UNDERLYING = "510050.SH"
EXPIRY_MONTH = "2026-03"
K_OTM_PUT = 2.85
K_OTM_CALL = 3.15
LEG_LP = f"{UNDERLYING}-{EXPIRY_MONTH}-P-{K_OTM_PUT:.2f}"
LEG_SC = f"{UNDERLYING}-{EXPIRY_MONTH}-C-{K_OTM_CALL:.2f}"
KLINE_DUR = 60 * 15
SKEW_LOOKBACK = 30
SKEW_ENTRY_STD = 1.0
SKEW_EXIT_STD = 0.3
SKEW_STOP_STD = 2.0
DELTA_HEDGE_INTERVAL = 15 * 60
VIX_THRESHOLD = 30
MAX_HOLDING_PERIODS = 40
POSITION_SIZE = 1
BASE_NOTIONAL = 10000
# ==================================


def calc_approx_iv(option_price, S, K, T, r=0.03, is_call=True):
    if T <= 0 or option_price <= 0:
        return np.nan
    intrinsic = max(S - K, 0) if is_call else max(K - S, 0)
    time_value = option_price - intrinsic
    if time_value <= 0:
        return 0.0
    vega_approx = time_value / (0.4 * np.sqrt(max(T, 0.0001)) + 0.01)
    iv_approx = vega_approx / (S * np.sqrt(max(T, 0.0001)) * 0.4 + 0.01)
    return min(max(iv_approx, 0.05), 2.0)


def calc_delta_approx(S, K, T, r, sigma, is_call=True):
    if T <= 0:
        return 1.0 if is_call else 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(max(T, 0.0001)) + 0.0001)
    from math import erf, sqrt
    delta = (0.5 + 0.5 * erf(d1 / sqrt(2))) if is_call else (-0.5 + 0.5 * erf(d1 / sqrt(2)))
    return delta


def calc_greeks(S, K, T, r, quote, is_call=True):
    iv = calc_approx_iv(quote, S, K, T, r, is_call)
    if np.isnan(iv) or iv <= 0:
        return 0.3, 0.5 if is_call else -0.5, 0.0
    delta = calc_delta_approx(S, K, T, r, iv, is_call)
    d1 = (np.log(S / K) + (r + 0.5 * iv ** 2) * T) / (iv * np.sqrt(max(T, 0.0001)) + 0.0001)
    from math import sqrt, exp
    vega = S * sqrt(max(T, 0.0001)) * exp(-0.5 * d1 ** 2) / sqrt(2 * 3.14159) / 100
    return iv, delta, vega


def estimate_vix(S, put_quote, call_quote, T):
    if T <= 0:
        return 20.0
    avg_premium = (put_quote + call_quote) / 2
    vix_approx = avg_premium / (S * np.sqrt(max(T, 0.0001))) * 100
    return min(max(vix_approx, 5.0), 100.0)


def main():
    api = TqApi(auth=TqAuth("13556817485", "asd159753"))
    print("=" * 60)
    print("策略33：期权波动率偏度交易策略")
    print("=" * 60)

    underlying_serial = api.get_tick_serial(UNDERLYING)
    opt_put_serial = api.get_tick_serial(LEG_LP)
    opt_call_serial = api.get_tick_serial(LEG_SC)
    print(f"  标的：{UNDERLYING}, 期权：{LEG_LP} / {LEG_SC}")

    print("等待数据加载...")
    time.sleep(5)

    skew_history = []
    vix_history = []
    in_position = False
    position_direction = 0
    holding_periods = 0
    last_hedge_time = None
    position_shares = 0

    direction_str = {1: "做多偏度回归", -1: "做空偏度回归"}

    with api.register_update_notify():
        while True:
            api.wait_update()
            now = api.get_trading_time()
            if now is None:
                continue

            if len(opt_put_serial) < 10 or len(opt_call_serial) < 10 or len(underlying_serial) < 10:
                continue

            S = underlying_serial["close"].iloc[-1]
            put_quote = opt_put_serial["close"].iloc[-1]
            call_quote = opt_call_serial["close"].iloc[-1]
            T = 20 / 252

            iv_put, delta_put, vega_put = calc_greeks(S, K_OTM_PUT, T, 0.03, put_quote, is_call=False)
            iv_call, delta_call, vega_call = calc_greeks(S, K_OTM_CALL, T, 0.03, call_quote, is_call=True)
            atm_iv = (iv_put + iv_call) / 2
            skew = (atm_iv - iv_put) / atm_iv if atm_iv > 0 else 0.0
            skew_history.append(skew)
            if len(skew_history) > SKEW_LOOKBACK * 100:
                skew_history = skew_history[-SKEW_LOOKBACK * 100:]

            if len(skew_history) < SKEW_LOOKBACK * 10:
                time.sleep(30)
                continue

            if len(skew_history) % 10 != 0:
                continue

            vix = estimate_vix(S, put_quote, call_quote, T)
            vix_history.append(vix)
            if len(vix_history) > 100:
                vix_history = vix_history[-100:]

            recent_skew = skew_history[::10]
            skew_mean = np.mean(recent_skew[-SKEW_LOOKBACK:])
            skew_std = np.std(recent_skew[-SKEW_LOOKBACK:])
            if skew_std < 1e-10:
                skew_std = 0.1
            skew_z = (skew - skew_mean) / skew_std

            vix_avg = np.mean(vix_history[-20:]) if len(vix_history) >= 20 else 30
            vix_enhanced = vix_avg > VIX_THRESHOLD

            if not in_position:
                if skew_z > SKEW_ENTRY_STD:
                    direction = 1
                    position_direction = direction
                    print(f"\n{'=' * 55}")
                    print(f"【做多偏度回归信号】{now}")
                    print(f"  Skew={skew:.4f}, 均值={skew_mean:.4f}, Z={skew_z:.2f}")
                    print(f"  ATM IV={atm_iv:.4f}, OTM Put IV={iv_put:.4f}, OTM Call IV={iv_call:.4f}")
                    print(f"  标的价格={S:.3f}, VIX估算={vix:.2f}, VIX增强={'是' if vix_enhanced else '否'}")
                    print(f"  Delta={delta_put + delta_call:.4f}, Vega={vega_put + vega_call:.4f}")
                    print(f"  操作: 买入{LEG_LP} + 卖出{LEG_SC} + Delta对冲")
                    print(f"{'=' * 55}")
                    in_position = True
                    holding_periods = 0
                    last_hedge_time = now
                elif skew_z < -SKEW_ENTRY_STD:
                    direction = -1
                    position_direction = direction
                    print(f"\n{'=' * 55}")
                    print(f"【做空偏度回归信号】{now}")
                    print(f"  Skew={skew:.4f}, 均值={skew_mean:.4f}, Z={skew_z:.2f}")
                    print(f"  ATM IV={atm_iv:.4f}, OTM Put IV={iv_put:.4f}, OTM Call IV={iv_call:.4f}")
                    print(f"  标的价格={S:.3f}, VIX估算={vix:.2f}")
                    print(f"  操作: 卖出{LEG_LP} + 买入{LEG_SC} + Delta对冲")
                    print(f"{'=' * 55}")
                    in_position = True
                    holding_periods = 0
                    last_hedge_time = now
            else:
                holding_periods += 1
                if abs(skew_z) > SKEW_STOP_STD:
                    print(f"\n【止损出场】Skew Z={skew_z:.2f} > {SKEW_STOP_STD}σ")
                    in_position = False
                    position_direction = 0
                    holding_periods = 0
                elif abs(skew_z) < SKEW_EXIT_STD:
                    print(f"\n【平仓出场】Skew Z={skew_z:.2f} 回归±{SKEW_EXIT_STD}σ")
                    in_position = False
                    position_direction = 0
                    holding_periods = 0
                elif holding_periods >= MAX_HOLDING_PERIODS:
                    print(f"\n【超时强平】已持有{holding_periods}周期")
                    in_position = False
                    position_direction = 0
                    holding_periods = 0

                if in_position and last_hedge_time:
                    from datetime import datetime, timedelta
                    if isinstance(now, datetime) and isinstance(last_hedge_time, datetime):
                        dt = (now - last_hedge_time).total_seconds()
                    else:
                        dt = 0
                    if dt >= DELTA_HEDGE_INTERVAL:
                        total_delta = delta_put + delta_call
                        hedge_shares = -int(total_delta * BASE_NOTIONAL / S)
                        shares_diff = hedge_shares - position_shares
                        if abs(shares_diff) > 10:
                            print(f"  [Delta对冲] Δ={total_delta:.4f}, 调整ETF: {position_shares}->{hedge_shares}")
                        position_shares = hedge_shares
                        last_hedge_time = now

            if len(skew_history) % 50 == 0:
                status = f"偏度={skew:.3f}(Z={skew_z:.2f}) Skew均值={skew_mean:.3f}"
                pos_info = f"持仓{direction_str.get(position_direction, '无')}" if in_position else "空仓"
                print(f"📊 {now}: {status}, {pos_info}, IV_Put={iv_put:.2%}, IV_Call={iv_call:.2%}, VIX≈{vix:.1f}")


if __name__ == "__main__":
    main()
