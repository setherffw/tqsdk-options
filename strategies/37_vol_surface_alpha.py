#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
策略37：波动率曲面预测Alpha策略
基于期权波动率曲面的形态特征（skew + smile + term structure）
构建波动率曲面预测的量化Alpha因子，用于期权做市或波动率交易
"""

import numpy as np
import pandas as pd
from tqsdk import TqApi, TqAuth
from tqsdk.opt import RiskEvaluation

# ========== 策略参数 ==========
UNDERLYING = "SHFE.rb2505"           # 标的合约
OPTION_SERIES = "SHFE.rb2505"        # 期权系列
INIT_PORTFOLIO = 2000000

# 波动率曲面参数
STRIKE_RANGE = 0.20                  # 执行价范围（标的价格的±20%）
ATM_THRESHOLD = 0.02                 # 平价期权判定阈值
OTM_MULTIPLIER = 0.05               # 虚值期权步进（5%）

# ========== 波动率曲面因子计算 ==========
def calc_iv_skew(iv_dict, spot_price, strikes):
    """计算波动率偏度（put skew 和 call skew）"""
    if len(iv_dict) < 3 or spot_price <= 0:
        return 0.0

    atm_key = None
    put_keys = []
    call_keys = []

    for k_str in iv_dict.keys():
        try:
            k = float(k_str)
        except:
            continue
        if abs(k - spot_price) / spot_price < ATM_THRESHOLD:
            atm_key = k_str
        elif k < spot_price:
            put_keys.append((k, k_str))
        else:
            call_keys.append((k, k_str))

    if atm_key is None or not put_keys or not call_keys:
        return 0.0

    atm_iv = iv_dict[atm_key]

    # Put skew: 虚值put的IV与ATM IV的差
    put_skew = 0.0
    if put_keys:
        otm_puts = [(k, s) for k, s in put_keys
                    if (spot_price - k) / spot_price > 0.02]
        if otm_puts:
            otm_put_skews = [iv_dict[s] - atm_iv for k, s in otm_puts]
            put_skew = np.mean(otm_put_skews)

    # Call skew: 虚值call的IV与ATM IV的差
    call_skew = 0.0
    if call_keys:
        otm_calls = [(k, s) for k, s in call_keys
                     if (k - spot_price) / spot_price > 0.02]
        if otm_calls:
            otm_call_skews = [iv_dict[s] - atm_iv for k, s in otm_calls]
            call_skew = np.mean(otm_call_skews)

    return put_skew, call_skew

def calc_term_structure(iv_series_dict, expiry_list):
    """计算期限结构（近月-远月IV差）"""
    if len(iv_series_dict) < 2 or len(expiry_list) < 2:
        return {}

    result = {}
    expirations = sorted(expiry_list)[:3]  # 最近3个到期月份

    for i in range(len(expirations) - 1):
        near_exp = expirations[i]
        far_exp = expirations[i + 1]
        near_iv = iv_series_dict.get(near_exp, {}).get("atm_iv", 0)
        far_iv = iv_series_dict.get(far_exp, {}).get("atm_iv", 0)
        result[f"{near_exp}_vs_{far_exp}"] = far_iv - near_iv

    return result

# ========== 波动率曲面预测Alpha因子 ==========
def calc_vol_surface_alpha(spot, iv_dict, term_structure):
    """
    综合波动率曲面信息，输出alpha因子信号
    alpha > 0: 波动率曲面偏高估（适合卖出）
    alpha < 0: 波动率曲面偏低估（适合买入）
    """
    if not iv_dict or spot <= 0:
        return 0.0

    # 1. Skew Alpha
    skews = calc_iv_skew(iv_dict, spot, list(iv_dict.keys()))
    put_skew, call_skew = skews

    # 2. Term Structure Alpha
    term_alpha = 0.0
    if term_structure:
        for key, diff in term_structure.items():
            # 近月IV < 远月IV (contango) -> 做空波动率
            # 近月IV > 远月IV (backwardation) -> 做多波动率
            term_alpha += diff * 0.5

    # 3. 波动率水平Alpha
    atm_ivs = [v for k, v in iv_dict.items() if abs(float(k) - spot) / spot < ATM_THRESHOLD]
    hist_iv_mean = 0.18  # 假设历史均值18%
    vol_level_alpha = 0.0
    if atm_ivs:
        avg_atm_iv = np.mean(atm_ivs)
        vol_level_alpha = (avg_atm_iv - hist_iv_mean) / hist_iv_mean

    # 综合Alpha
    alpha = 0.4 * (put_skew + call_skew) / 0.05 + 0.3 * term_alpha + 0.3 * vol_level_alpha

    return alpha

# ========== 策略主体 ==========
def main():
    api = TqApi(auth=TqAuth("auto", "auto"))

    print(f"[策略37] 波动率曲面预测Alpha策略启动 | 标的: {UNDERLYING}")

    underlying_quote = api.get_quote(UNDERLYING)
    atm_strike = underlying_quote.last_price

    # 模拟构建波动率曲面数据（实际使用TqOptionData获取完整曲面）
    strikes = [atm_strike * (1 - i * OTM_MULTIPLIER) for i in range(5, 0, -1)] + \
              [atm_strike * (1 + i * OTM_MULTIPLIER) for i in range(1, 6)]
    strikes = sorted(set([round(s, -1) for s in strikes]))

    print(f"[策略37] ATM执行价: {atm_strike:.2f} | 监控strike数: {len(strikes)}")

    day_count = 0

    while True:
        api.wait_update()

        spot = underlying_quote.last_price
        if spot <= 0 or np.isnan(spot):
            continue

        day_count += 1

        # 每10个周期评估一次波动率曲面
        if day_count % 10 != 0:
            continue

        # 模拟波动率曲面数据（实际从TqOptionData获取）
        # 这里用随机游走模拟IV曲面（演示用）
        base_iv = 0.20 + np.random.randn() * 0.03
        iv_dict = {}
        for k in strikes:
            moneyness = (k - spot) / spot
            iv = base_iv * (1 + moneyness * 0.5) + np.random.randn() * 0.01
            iv_dict[str(k)] = max(0.05, min(1.0, iv))

        term_structure = {
            "1m_vs_2m": 0.02 + np.random.randn() * 0.005,
            "2m_vs_3m": 0.01 + np.random.randn() * 0.003,
        }

        alpha = calc_vol_surface_alpha(spot, iv_dict, term_structure)

        print(f"[策略37] Day {day_count} | Spot={spot:.2f} | Alpha={alpha:.4f}")
        print(f"         Put Skew={calc_iv_skew(iv_dict, spot, strikes)[0]:.4f}")
        print(f"         Term={list(term_structure.values())}")

        # Alpha 交易逻辑
        # alpha > 0.1: 波动率曲面高估 -> 卖出期权（做空波动率）
        # alpha < -0.1: 波动率曲面低估 -> 买入期权（做多波动率）
        # |alpha| < 0.05: 平仓

        if alpha > 0.1:
            print(f"         >>> 信号: 波动率曲面高估 | 建议卖出期权")
        elif alpha < -0.1:
            print(f"         >>> 信号: 波动率曲面低估 | 建议买入期权")
        else:
            print(f"         >>> 信号: 中性 | 观望")

    api.close()

if __name__ == "__main__":
    main()
