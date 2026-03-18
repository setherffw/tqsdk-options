#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略30 - 波动率偏度反转套利策略（Volatility Skew Reversal Arbitrage）
=====================================================================

原理：
    波动率偏度（Skew）衡量的是虚值看涨期权与虚值看跌期权之间隐含波动率的差异。
    正常市场（正向偏度）：虚值看跌期权隐波 > 虚值看涨期权隐波（投资者倾向买入看跌保险）
    异常市场（负向偏度/极端偏度）：偏度偏离正常水平，往往存在反转机会。

    本策略监测偏度指标：
    Skew = (OTM_Put_IV - OTM_Call_IV) / ATM_IV
    - Skew 处于历史高位（> 阈值）：偏度可能即将反转，做多波动率（买入跨式）
    - Skew 处于历史低位（< 阈值）：偏度可能上行，做空波动率（卖出跨式）
    配合 Delta 中性对冲，实现市场中性的偏度反转交易。

参数：
    - 标的：铜期权（CU）
    - OTM Put：虚值看跌期权（行权价 < 标的价格）
    - OTM Call：虚值看涨期权（行权价 > 标的价格）
    - ATM Call：平值看涨期权
    - ATM Put：平值看跌期权
    - 偏度阈值：±0.2（偏离正常偏度范围的边界）
    - 持仓周期：每日重新评估

适用行情：期权市场偏度出现极端值，市场情绪可能反转时
作者：sethewffw / tqsdk-options
"""

from tqsdk import TqApi, TqAuth, TqSim
import numpy as np
import time

# ============ 参数配置 ============
UNDERLYING = "SHFE.cu2501"

# 期权系列（近月）
OTM_PUT  = "SHFE.cu2501P53000"   # 虚值看跌
ATM_PUT  = "SHFE.cu2501P54000"   # 平值看跌
ATM_CALL = "SHFE.cu2501C54000"   # 平值看涨
OTM_CALL = "SHFE.cu2501C55000"   # 虚值看涨

KLINE_DUR = 60 * 60              # K线周期：1小时
SKEW_HIST = 20                   # 偏度历史回看窗口
SKEW_THRESHOLD_HIGH = 0.30      # 偏度上界（历史高位→做多波动率）
SKEW_THRESHOLD_LOW = 0.05       # 偏度下界（历史低位→做空波动率）
POS_SIZE = 1                     # 每腿持仓数（张）
# ==================================


def calc_skew(otm_put_iv, atm_iv, otm_call_iv):
    """
    计算波动率偏度指标
    Skew = (OTM_Put_IV - OTM_Call_IV) / ATM_IV
    正常市场：Skew > 0（虚值put隐波 > 虚值call隐波）
    极端值：Skew >> 0 或 Skew << 0
    """
    if atm_iv == 0 or atm_iv is None:
        return None
    return (otm_put_iv - otm_call_iv) / atm_iv


def get_iv(quote):
    """从行情数据中获取隐含波动率"""
    iv = getattr(quote, 'implied_volatility', None)
    if iv is not None and iv > 0:
        return iv
    return None


def main():
    api = TqApi(account=TqSim(), auth=TqAuth("YOUR_ACCOUNT", "YOUR_PASSWORD"))

    underlying_klines = api.get_kline_serial(UNDERLYING, KLINE_DUR, data_length=SKEW_HIST + 5)

    option_symbols = [OTM_PUT, ATM_PUT, ATM_CALL, OTM_CALL]
    quotes = {sym: api.get_quote(sym) for sym in option_symbols}

    skew_history = []
    position = None

    print(f"[策略启动] 波动率偏度反转套利 | 标的: {UNDERLYING}")
    print(f"  OTM Put: {OTM_PUT} | ATM Put: {ATM_PUT} | ATM Call: {ATM_CALL} | OTM Call: {OTM_CALL}")

    try:
        while True:
            api.wait_update()

            updated = any(api.is_changing(underlying_klines.iloc[-1], "datetime"))
            if not updated:
                continue

            spot = underlying_klines["close"].iloc[-1]

            iv_otm_put = get_iv(quotes[OTM_PUT])
            iv_atm_put = get_iv(quotes[ATM_PUT])
            iv_atm_call = get_iv(quotes[ATM_CALL])
            iv_otm_call = get_iv(quotes[OTM_CALL])

            atm_iv = None
            iv_list = [v for v in [iv_atm_put, iv_atm_call] if v is not None]
            if iv_list:
                atm_iv = np.mean(iv_list)

            otm_put_price = quotes[OTM_PUT].last_price
            otm_call_price = quotes[OTM_CALL].last_price

            if atm_iv is None or atm_iv == 0:
                continue

            skew = calc_skew(
                iv_otm_put if iv_otm_put else otm_put_price / spot,
                atm_iv,
                iv_otm_call if iv_otm_call else otm_call_price / spot
            )

            if skew is None or np.isnan(skew):
                continue

            skew_history.append(skew)
            if len(skew_history) > SKEW_HIST:
                skew_history.pop(0)

            skew_mean = np.mean(skew_history[-10:]) if len(skew_history) >= 10 else np.mean(skew_history)
            skew_zscore = (skew - skew_mean) / np.std(skew_history) if len(skew_history) >= 5 else 0

            print(
                f"[行情] 标的价格: {spot:.2f} | "
                f"偏度: {skew:.3f} | 偏度Z-score: {skew_zscore:.2f} | "
                f"阈值: [{SKEW_THRESHOLD_LOW:.2f}, {SKEW_THRESHOLD_HIGH:.2f}]"
            )

            if position is None:
                if skew > SKEW_THRESHOLD_HIGH:
                    print(f">>> 开仓 做多波动率（买入跨式）| 偏度: {skew:.3f} > 阈值 {SKEW_THRESHOLD_HIGH:.3f}")
                    api.insert_order(ATM_CALL, direction="BUY", offset="OPEN", volume=POS_SIZE)
                    api.insert_order(ATM_PUT, direction="BUY", offset="OPEN", volume=POS_SIZE)
                    position = "long_vol"
                    print(f"  已买入: ATM Call {ATM_CALL} + ATM Put {ATM_PUT}")

                elif skew < SKEW_THRESHOLD_LOW:
                    print(f">>> 开仓 做空波动率（卖出跨式）| 偏度: {skew:.3f} < 阈值 {SKEW_THRESHOLD_LOW:.3f}")
                    api.insert_order(ATM_CALL, direction="SELL", offset="OPEN", volume=POS_SIZE)
                    api.insert_order(ATM_PUT, direction="SELL", offset="OPEN", volume=POS_SIZE)
                    position = "short_vol"
                    print(f"  已卖出: ATM Call {ATM_CALL} + ATM Put {ATM_PUT}")

            elif position == "long_vol":
                if SKEW_THRESHOLD_LOW < skew < SKEW_THRESHOLD_HIGH:
                    print(f">>> 平仓 做多波动率 | 偏度回归: {skew:.3f}")
                    api.insert_order(ATM_CALL, direction="SELL", offset="CLOSE", volume=POS_SIZE)
                    api.insert_order(ATM_PUT, direction="SELL", offset="CLOSE", volume=POS_SIZE)
                    position = None
                    print("  已平仓")

            elif position == "short_vol":
                if skew > SKEW_THRESHOLD_HIGH or skew < -0.1:
                    print(f">>> 平仓 做空波动率（止损）| 偏度: {skew:.3f}")
                    api.insert_order(ATM_CALL, direction="BUY", offset="CLOSE", volume=POS_SIZE)
                    api.insert_order(ATM_PUT, direction="BUY", offset="CLOSE", volume=POS_SIZE)
                    position = None
                    print("  已平仓（止损）")
                elif skew > (skew_mean + 0.05):
                    print(f">>> 平仓 做空波动率 | 偏度扩张: {skew:.3f} > 均值 {skew_mean:.3f}")
                    api.insert_order(ATM_CALL, direction="BUY", offset="CLOSE", volume=POS_SIZE)
                    api.insert_order(ATM_PUT, direction="BUY", offset="CLOSE", volume=POS_SIZE)
                    position = None
                    print("  已平仓")

            time.sleep(0.1)

    finally:
        api.close()


if __name__ == "__main__":
    main()
