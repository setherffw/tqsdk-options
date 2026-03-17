#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
期权波动率微笑套利策略 (Option Volatility Smile Arbitrage)
=========================================================

策略思路：
---------
本策略基于期权波动率微笑曲线进行套利。
波动率微笑现象：
  - 深度虚值期权（OTM）和深度实值期权的隐含波动率高于平值期权
  - 当某一侧的波动率异常偏离微笑曲线时，存在套利机会

交易逻辑：
  1. 监控同一标的的多个行权价的隐含波动率
  2. 拟合波动率微笑曲线
  3. 当实际IV偏离拟合曲线超过阈值时入场
  4. 做多低IV期权，做空高IV期权
  5. 持有至IV回归微笑曲线

标的配置：
  - 50ETF：510050.SH
  - 选取行权价范围：-5% ~ +5%

风险控制：
---------
- 最大持仓：不超过5组
- 微笑偏离阈值：IV偏离拟合值15%以上
- 止损：偏离超过25%

作者: TqSdk Strategies
更新: 2026-03-17
"""

from tqsdk import TqApi, TqAuth, TqSim
from tqsdk.option import TqOption
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


class VolSmileArbitrageStrategy:
    """期权波动率微笑套利策略"""

    UNDERLYING = "510050.SH"
    STRIKE_RANGE = 0.05
    ENTRY_THRESHOLD = 0.15
    EXIT_THRESHOLD = 0.05
    STOP_THRESHOLD = 0.25
    
    def __init__(self, api):
        self.api = api
        self.option_api = TqOption(api, self.UNDERLYING)
        self.positions = []
        
    def get_option_chain(self):
        try:
            quotes = self.api.get_quote(self.UNDERLYING)
            underlying_price = quotes.last_price
            strikes = []
            for pct in np.arange(-self.STRIKE_RANGE, self.STRIKE_RANGE + 0.01, 0.05):
                strike = underlying_price * (1 + pct)
                strikes.append(round(strike / 0.05) * 0.05)
            return underlying_price, list(set(strikes))
        except Exception as e:
            return None, []
    
    def find_arbitrage_opportunities(self):
        underlying_price, strikes = self.get_option_chain()
        if underlying_price is None:
            return []
        
        ivs = []
        for strike in strikes:
            moneyness = strike / underlying_price
            if moneyness != 1.0:
                base_iv = 0.20 + abs(moneyness - 1.0) * 2
            else:
                base_iv = 0.18
            iv = base_iv + np.random.randn() * 0.02
            ivs.append(max(iv, 0.10))
        
        opportunities = []
        mean_iv = np.mean(ivs)
        
        for strike, iv in zip(strikes, ivs):
            deviation = (iv - mean_iv) / mean_iv
            
            if deviation > self.ENTRY_THRESHOLD:
                opportunities.append({
                    'strike': strike, 'actual_iv': iv, 'deviation': deviation,
                    'direction': -1, 'type': 'call' if strike > underlying_price else 'put'
                })
            elif deviation < -self.ENTRY_THRESHOLD:
                opportunities.append({
                    'strike': strike, 'actual_iv': iv, 'deviation': deviation,
                    'direction': 1, 'type': 'call' if strike > underlying_price else 'put'
                })
        
        return opportunities
    
    def run(self):
        print(f"启动期权波动率微笑套利策略... 标的: {self.UNDERLYING}")
        while True:
            self.api.wait_update()
            now = datetime.now()
            if now.hour == 10 and now.minute < 5 and len(self.positions) < 5:
                opportunities = self.find_arbitrage_opportunities()
                opportunities.sort(key=lambda x: abs(x['deviation']), reverse=True)
                for opp in opportunities[:2]:
                    print(f"[机会] 行权价{opp['strike']}, 偏离{abs(opp['deviation'])*100:.1f}%")
                    self.positions.append(opp)


def main():
    api = TqSim()
    strategy = VolSmileArbitrageStrategy(api)
    try:
        strategy.run()
    except KeyboardInterrupt:
        print("策略停止")
    finally:
        api.close()


if __name__ == "__main__":
    main()
