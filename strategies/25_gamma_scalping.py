#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
期权Gamma Scalping动态对冲策略 (Options Gamma Scalping Strategy)
================================================================
Gamma Scalping是一种期权Delta中性交易策略，通过动态对冲来捕捉Gamma收益。
核心：卖出期权建立空头Delta，通过反复调整期货仓位从波动中获取收益。
"""

from tqsdk import TqApi, TqSim, TqOption
import numpy as np


class GammaScalpingStrategy:
    """期权Gamma Scalping策略"""

    UNDERLYING = "510050.SH"
    STRIKE_OTM_PCT = 0.03
    DELTA_THRESHOLD = 0.05
    REBALANCE_INTERVAL = 60

    def __init__(self, api):
        self.api = api
        self.underlying_quote = api.get_quote(self.UNDERLYING)
        self.option_api = TqOption(api)
        self.future_pos = 0
        self.prev_price = 0
        self.last_rebalance = 0

    def _get_atm_strike(self):
        price = self.underlying_quote.last_price
        return round(price / 0.5) * 0.5

    def _rebalance(self):
        price = self.underlying_quote.last_price
        if self.prev_price == 0:
            self.prev_price = price
            return

        price_change = price - self.prev_price

        if abs(price_change) > 0.05:
            if price_change > 0:
                self.future_pos += 100
                print(f"[对冲] 价格上涨，买入期货: 100")
            else:
                self.future_pos -= 100
                print(f"[对冲] 价格下跌，卖出期货: 100")

        self.prev_price = price

    def run(self):
        print("期权Gamma Scalping策略启动")
        while True:
            self.api.wait_update()


if __name__ == "__main__":
    api = TqSim()
    strategy = GammaScalpingStrategy(api)
    strategy.run()
