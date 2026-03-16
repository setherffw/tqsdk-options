#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
期权期限结构套利策略 (Options Term Structure Arbitrage Strategy)
=================================================================
基于不同到期日期权的波动率差异进行套利。Contango做空结构，Backwardation做多结构。
"""

from tqsdk import TqApi, TqSim, TqOption
import numpy as np
from datetime import datetime, timedelta


class TermStructureArbitrage:
    """期权期限结构套利策略"""

    UNDERLYING = "510050.SH"
    NEAR_EXPIRY_DAYS = 30
    FAR_EXPIRY_DAYS = 60
    ENTRY_CONTANGO = 0.03
    EXIT_CONTANGO = 0.01
    REBALANCE_DAYS = 5

    def __init__(self, api):
        self.api = api
        self.option_api = TqOption(api)
        self.underlying_quote = api.get_quote(self.UNDERLYING)
        self.position_direction = None

    def _get_near_far_contracts(self):
        price = self.underlying_quote.last_price
        strike = round(price / 0.5) * 0.5
        now = datetime.now()
        near_exp = (now + timedelta(days=self.NEAR_EXPIRY_DAYS)).strftime("%y%m")
        far_exp = (now + timedelta(days=self.FAR_EXPIRY_DAYS)).strftime("%y%m")
        return {"strike": strike, "near_exp": near_exp, "far_exp": far_exp}

    def _calculate_iv_spread(self):
        # 简化模拟
        return 0.03

    def run(self):
        print("期权期限结构套利策略启动")
        while True:
            self.api.wait_update()


if __name__ == "__main__":
    api = TqSim()
    strategy = TermStructureArbitrage(api)
    strategy.run()
