#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略29 - 波动率期限结构套利策略（Volatility Term Structure Arbitrage）
=====================================================================

原理：
    期权隐含波动率具有明显的期限结构特征（近月/远月价差关系）。
    当近月波动率相对于远月偏高（期限结构陡峭），未来大概率会平坦化；
    当近月波动率相对于远月偏低（期限结构平坦或倒转），未来大概率会陡峭化。

    本策略利用波动率期限结构的均值回归特性：
    - 做空近月跨式期权组合（做空期限结构前端波动率）
    - 配合 Delta 对冲，保持市场中性的情况下赚取波动率回归收益

    核心逻辑：
    期限结构因子 = IV_near / IV_far
    - 因子 > 1（期限结构陡峭）：近月波动率高于远月，做空期限结构（Short Calendar）
    - 因子 < 1（期限结构倒转）：近月波动率低于远月，做多期限结构（Long Calendar）

参数：
    - 标的：豆粕期权（M）
    - 近月合约：近月主力看涨+看跌（ATM）
    - 远月合约：远月主力看涨+看跌（ATM）
    - 波动率阈值：0.05（上下界）
    - Delta对冲频率：按需调整

适用行情：波动率期限结构出现极端偏离时
作者：sethewffw / tqsdk-options
"""

from tqsdk import TqApi, TqAuth, TqSim
import numpy as np
import time

# ============ 参数配置 ============
UNDERLYING = "DCE.m2501"       # 标的：豆粕期货主力
NEAR_EXPIRY = "m2504"          # 近月到期月份（如m2504）
FAR_EXPIRY = "m2505"          # 远月到期月份（如m2505）

CALL_NEAR = f"DCE.m{NEAR_EXPIRY}C"   # 近月看涨
PUT_NEAR  = f"DCE.m{NEAR_EXPIRY}P"   # 近月看跌
CALL_FAR  = f"DCE.m{FAR_EXPIRY}C"    # 远月看涨
PUT_FAR   = f"DCE.m{FAR_EXPIRY}P"    # 远月看跌

KLINE_DUR = 60 * 60            # K线周期：1小时
VOL_PERIOD = 20                # 隐波计算回看周期（用于估算）
Z_OPEN = 0.5                   # 期限结构Z-score开仓阈值
Z_CLOSE = 0.1                 # 平仓阈值
POS_SIZE = 1                   # 每腿持仓数（张）
# ==================================

# 波动率估算辅助函数（基于历史收益率的简化隐波估算）
def estimate_iv_from_hist(klines, period=20):
    """用历史波动率估算隐含波动率（简化模型，不精确但可参考）"""
    if len(klines) < period + 1:
        return None
    rets = klines["close"].pct_change().dropna()
    if len(rets) < period:
        return None
    return rets[-period:].std() * np.sqrt(252)


def main():
    api = TqApi(account=TqSim(), auth=TqAuth("YOUR_ACCOUNT", "YOUR_PASSWORD"))

    # 订阅标的期货K线
    underlying_klines = api.get_kline_serial(UNDERLYING, KLINE_DUR, data_length=VOL_PERIOD + 5)

    # 订阅所有相关期权合约行情
    option_symbols = [CALL_NEAR, PUT_NEAR, CALL_FAR, PUT_FAR]
    quotes = {sym: api.get_quote(sym) for sym in option_symbols}

    # 初始化Delta对冲持仓
    position = {}   # {sym: pos}
    entry_ratio = None

    print(f"[策略启动] 波动率期限结构套利")
    print(f"  标的: {UNDERLYING} | 近月: {NEAR_EXPIRY} | 远月: {FAR_EXPIRY}")

    try:
        while True:
            api.wait_update()

            # 等待期权行情更新
            updated = any(api.is_changing(quotes[sym]) for sym in option_symbols)
            if not updated:
                continue

            # 获取标的价格
            spot = underlying_klines["close"].iloc[-1]

            # 获取期权价格（权利金）
            call_near_price = quotes[CALL_NEAR].last_price
            put_near_price = quotes[PUT_NEAR].last_price
            call_far_price = quotes[CALL_FAR].last_price
            put_far_price = quotes[PUT_FAR].last_price

            # 获取隐含波动率（若API提供）
            iv_call_near = getattr(quotes[CALL_NEAR], 'implied_volatility', None)
            iv_put_near = getattr(quotes[PUT_NEAR], 'implied_volatility', None)
            iv_call_far = getattr(quotes[CALL_FAR], 'implied_volatility', None)
            iv_put_far = getattr(quotes[PUT_FAR], 'implied_volatility', None)

            # 用近月call+put的均价代表近月波动率水平
            iv_near = iv_call_near if iv_call_near is not None else (call_near_price + put_near_price) / 2
            iv_far = iv_call_far if iv_call_far is not None else (call_far_price + put_far_price) / 2

            # ---- 计算期限结构因子 ----
            if iv_far != 0:
                term_structure = iv_near / iv_far
            else:
                term_structure = 1.0

            print(
                f"[行情] 标的价格: {spot:.2f} | "
                f"近月Call: {call_near_price:.2f} Put: {put_near_price:.2f} | "
                f"远月Call: {call_far_price:.2f} Put: {put_far_price:.2f} | "
                f"期限结构: {term_structure:.3f}"
            )

            # ---- 获取持仓状态 ----
            if not position:
                pos_call_near = api.get_position(CALL_NEAR)
                pos_put_near = api.get_position(PUT_NEAR)
                pos_call_far = api.get_position(CALL_FAR)
                pos_put_far = api.get_position(PUT_FAR)

                total_pos = (
                    pos_call_near.pos_short + pos_put_near.pos_short +
                    pos_call_far.pos_long + pos_put_far.pos_long
                )
                if total_pos > 0:
                    position[CALL_NEAR] = pos_call_near
                    position[PUT_NEAR] = pos_put_near
                    position[CALL_FAR] = pos_call_far
                    position[PUT_FAR] = pos_put_far

            # ---- 无持仓：根据期限结构开仓 ----
            if not position:
                # 期限结构陡峭（>1+Z_OPEN）：做空近月，做多远月（Short Calendar）
                if term_structure > 1 + Z_OPEN:
                    print(f">>> 开仓 Short Calendar | 期限结构: {term_structure:.3f}")
                    api.insert_order(CALL_NEAR, direction="SELL", offset="OPEN", volume=POS_SIZE)
                    api.insert_order(PUT_NEAR, direction="SELL", offset="OPEN", volume=POS_SIZE)
                    api.insert_order(CALL_FAR, direction="BUY", offset="OPEN", volume=POS_SIZE)
                    api.insert_order(PUT_FAR, direction="BUY", offset="OPEN", volume=POS_SIZE)
                    entry_ratio = term_structure
                    position = {CALL_NEAR: "short", PUT_NEAR: "short",
                                 CALL_FAR: "long", PUT_FAR: "long"}
                    print("  已开: 卖近月Call+Put | 买远月Call+Put")

                # 期限结构倒转（<1-Z_OPEN）：做多近月，做空远月（Long Calendar）
                elif term_structure < 1 - Z_OPEN:
                    print(f">>> 开仓 Long Calendar | 期限结构: {term_structure:.3f}")
                    api.insert_order(CALL_NEAR, direction="BUY", offset="OPEN", volume=POS_SIZE)
                    api.insert_order(PUT_NEAR, direction="BUY", offset="OPEN", volume=POS_SIZE)
                    api.insert_order(CALL_FAR, direction="SELL", offset="OPEN", volume=POS_SIZE)
                    api.insert_order(PUT_FAR, direction="SELL", offset="OPEN", volume=POS_SIZE)
                    entry_ratio = term_structure
                    position = {CALL_NEAR: "long", PUT_NEAR: "long",
                                 CALL_FAR: "short", PUT_FAR: "short"}
                    print("  已开: 买近月Call+Put | 卖远月Call+Put")

            # ---- 有持仓：根据期限结构平仓 ----
            elif entry_ratio is not None:
                # 平仓条件：期限结构回归到接近1
                if abs(term_structure - 1.0) < Z_CLOSE:
                    print(f">>> 平仓 | 期限结构回归: {term_structure:.3f}")
                    for sym, side in position.items():
                        if side == "short":
                            api.insert_order(sym, direction="BUY", offset="CLOSE", volume=POS_SIZE)
                        elif side == "long":
                            api.insert_order(sym, direction="SELL", offset="CLOSE", volume=POS_SIZE)
                    position = {}
                    entry_ratio = None
                    print("  已平全部仓位")

            time.sleep(0.1)

    finally:
        api.close()


if __name__ == "__main__":
    main()
