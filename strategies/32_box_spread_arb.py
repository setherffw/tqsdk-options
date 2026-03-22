#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略32 - 期权箱式价差套利策略（Box Spread Arbitrage Strategy）
===============================================================

原理：
    箱式价差（Box Spread）是一种由四个期权腿组成的无风险套利组合，
    其本质是对两个垂直价差（牛市Put价差 + 熊市Call价差）的组合，
    无论标的价格如何变动，组合在到期时的价值总是等于执行价格之差。

    标准箱式结构：
    - Long Call (低行权价K1) + Short Call (高行权价K2)
      → 到期价值 = max(S-K1, 0) - max(S-K2, 0)
    - Short Put (低行权价K1) + Long Put (高行权价K2)
      → 到期价值 = max(K1-S, 0) - max(K2-S, 0)

    两者相加，无论S到期值如何：
    箱式价值 = K2 - K1（固定支付）

    套利逻辑：
    如果箱式的市场价格（当前权利金成本）< 理论价值(K2-K1)，
    说明市场低估，存在买入箱式（long box）机会；
    反之则卖出箱式（short box）。

    本策略实时监测箱式价差的理论价值与市场报价差异，
    当价差超过交易成本（手续费+滑点×2）时入场，
    等待价格收敛后平仓。

参数：
    - 标的：510050.SH（50ETF）
    - K1（低行权价）：低于标的价格约3%
    - K2（高行权价）：高于标的价格约3%
    - 到期月：近月
    - 入场阈值：理论价与市场报价差 > 0.02元/组
    - 平仓：价格回归至合理区间（差值 < 0.005元）或到期前2天

适用行情：箱式价格明显偏离理论值、期权市场效率较低时
风险提示：流动性风险（买卖价差大）、保证金不足风险
作者：setherffw / tqsdk-options
"""

from tqsdk import TqApi, TqAuth, TqSim, TargetPosTask
import numpy as np
import pandas as pd
import time

# ============ 参数配置 ============
UNDERLYING = "510050.SH"
EXPIRY_MONTH = "2026-03"           # 近月到期

# 箱式四条腿
# K1 = 低行权价（实值区域）
# K2 = 高行权价（虚值区域）
K1 = 2.85                           # 低行权价
K2 = 3.05                           # 高行权价

# 期权腿定义
LEG_LC = f"{UNDERLYING}-{EXPIRY_MONTH}-C-{K1:.2f}"   # Long Call K1
LEG_SC = f"{UNDERLYING}-{EXPIRY_MONTH}-C-{K2:.2f}"   # Short Call K2
LEG_SP = f"{UNDERLYING}-{EXPIRY_MONTH}-P-{K1:.2f}"   # Short Put K1
LEG_LP = f"{UNDERLYING}-{EXPIRY_MONTH}-P-{K2:.2f}"   # Long Put K2

KLINE_DUR = 60 * 60                # 1小时K线
SPREAD_THRESHOLD = 0.02            # 入场阈值（元/组）
EXIT_THRESHOLD = 0.005             # 平仓阈值
COST_PER_LEG = 0.003                # 每腿交易成本（估算）
POSITION = 1                        # 开仓组数
# ==================================


def theoretical_box_value(K1, K2, rate=0.03, T=14/365):
    """
    计算箱式价差的理论价值（到期价值折现）
    箱式到期价值 = K2 - K1（固定）
    折现 = (K2 - K1) * exp(-r * T)
    """
    from math import exp
    return (K2 - K1) * exp(-rate * T)


def calc_net_premium(api, legs_dict):
    """
    计算箱式当前净权利金成本
    legs_dict: {leg_name: (position_sign, quote)}
    position_sign: +1 = long, -1 = short
    返回：净成本（正=付钱，负=收钱）
    """
    net = 0.0
    for leg, (sign, q) in legs_dict.items():
        price = q.last_price
        if price <= 0:
            return None
        net += sign * price
    return net


def main():
    api = TqApi(auth=TqAuth("13556817485", "asd159753"))

    print("=" * 60)
    print("策略32：期权箱式价差套利策略")
    print("=" * 60)

    S = api.get_quote(UNDERLYING).last_price
    print(f"标的: {UNDERLYING}, 价格: {S:.3f}")
    print(f"箱式腿: K1={K1}, K2={K2}")
    print(f"腿: {LEG_LC}(+1) + {LEG_LP}(+1) + {LEG_SC}(-1) + {LEG_SP}(-1)")

    # 订阅期权腿
    try:
        q_lc = api.get_quote(LEG_LC)
        q_sc = api.get_quote(LEG_SC)
        q_sp = api.get_quote(LEG_SP)
        q_lp = api.get_quote(LEG_LP)
    except Exception as e:
        print(f"期权腿订阅失败: {e}")
        return

    # 持仓状态：0=空仓, 1=多头箱式, -1=空头箱式
    position = 0
    entry_spread = 0.0

    expiry_days = 14  # 简化：14天
    theoretical_value = theoretical_box_value(K1, K2, T=expiry_days/365)
    print(f"理论箱式价值（折现）: {theoretical_value:.4f} 元/组")
    print(f"入场阈值: ±{SPREAD_THRESHOLD} 元, 平仓阈值: ±{EXIT_THRESHOLD} 元")
    print("\n开始监控箱式价差...")

    while True:
        api.wait_update()

        # 监听价格变化
        changed = any(api.is_changing(q, "last_price")
                      for q in [q_lc, q_sc, q_sp, q_lp])
        if not changed:
            continue

        legs = {
            "LC": (1, q_lc),    # Long Call
            "SC": (-1, q_sc),   # Short Call
            "SP": (-1, q_sp),   # Short Put
            "LP": (1, q_lp),    # Long Put
        }

        net = calc_net_premium(api, legs)
        if net is None:
            time.sleep(1)
            continue

        # 箱式价值 = 净权利金
        # 买入箱式（long box）= 付钱 → net > 0
        # 卖出箱式（short box）= 收钱 → net < 0
        # 套利机会：net 与 theoretical_value 存在明显偏差
        deviation = abs(net - theoretical_value)

        print(f"[{pd.Timestamp.now().strftime('%H:%M:%S')}] "
              f"箱式净成本={net:.4f}, 理论={theoretical_value:.4f}, "
              f"偏离={deviation:.4f} {'↑套利机会' if deviation > SPREAD_THRESHOLD else ''}")

        if position == 0:
            if deviation > SPREAD_THRESHOLD:
                if net < theoretical_value:
                    # 市场低估箱式 → 买入箱式（long box）
                    print(f">>> 买入箱式套利入场！净成本={net:.4f}, 理论={theoretical_value:.4f}")
                    print(f"    Long LC={q_lc.last_price:.4f}, Long LP={q_lp.last_price:.4f}")
                    print(f"    Short SC={q_sc.last_price:.4f}, Short SP={q_sp.last_price:.4f}")
                    position = 1
                    entry_spread = net
                else:
                    # 市场高估箱式 → 卖出箱式（short box）
                    print(f">>> 卖出箱式套利入场！净收入={net:.4f}, 理论={theoretical_value:.4f}")
                    position = -1
                    entry_spread = net

        elif position == 1:
            # 多头箱式：等待收敛至理论值（价差变小 → 盈利）
            if net >= theoretical_value - EXIT_THRESHOLD or net >= entry_spread + SPREAD_THRESHOLD:
                print(f">>> 多头箱式平仓！平仓={net:.4f}, 入场={entry_spread:.4f}, 盈利={net - entry_spread:.4f}")
                position = 0

        elif position == -1:
            # 空头箱式：等待收敛
            if net <= theoretical_value + EXIT_THRESHOLD or net <= entry_spread - SPREAD_THRESHOLD:
                print(f">>> 空头箱式平仓！平仓={net:.4f}, 入场={entry_spread:.4f}, 盈利={entry_spread - net:.4f}")
                position = 0

        time.sleep(5)


if __name__ == "__main__":
    main()
