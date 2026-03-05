#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略11 - 波动率交易策略（Volatility Trading）
原理：
    买入跨式套利（Long Straddle）+ 波动率趋势跟随
    当预期波动率上升时买入跨式，当波动率回归时平仓

参数：
    - 标的合约：SHFE.if2505
    - ATM看涨期权：M2405C5400
    - ATM看跌期权：M2405P5400
    - 开仓波动率阈值：18%
    - 平仓波动率阈值：14%
    - 仓位：1组

适用行情：预期重大事件前后波动率上升
作者：setherffw / tqsdk-options
"""

from tqsdk import TqApi, TqAuth, TqSim
import numpy as np

# ============ 参数配置 ============
UNDERLYING = "SHFE.if2505"       # 标的合约
CALL_SYMBOL = "M2405C5400"      # ATM看涨期权
PUT_SYMBOL = "M2405P5400"       # ATM看跌期权
KLINE_DURATION = 60 * 60         # 1小时K线
OPEN_IV = 18.0                   # 开仓波动率阈值(%)
CLOSE_IV = 14.0                  # 平仓波动率阈值(%)
VOLUME = 1                       # 交易组数


def calc_historical_volatility(close_prices, period=20):
    """计算历史波动率"""
    returns = np.diff(np.log(close_prices))
    hv = np.std(returns) * np.sqrt(252) * 100  # 年化波动率
    return hv


def main():
    api = TqApi(account=TqSim(), auth=TqAuth("账号", "密码"))
    print("启动：波动率交易策略")
    
    underlying = api.get_quote(UNDERLYING)
    call_opt = api.get_quote(CALL_SYMBOL)
    put_opt = api.get_quote(PUT_SYMBOL)
    
    klines = api.get_kline_serial(UNDERLYING, KLINE_DURATION, data_length=100)
    
    position = 0  # 0: 空仓, 1: 持有跨式组合
    
    while True:
        api.wait_update()
        
        if api.is_changing(underlying):
            close_prices = klines["close"].values
            hv = calc_historical_volatility(close_prices)
            
            call_price = call_opt.last_price
            put_price = put_opt.last_price
            
            print(f"标的: {underlying.last_price}, 认购: {call_price:.2f}, "
                  f"认沽: {put_price:.2f}, HV: {hv:.2f}%")
            
            if position == 0:
                # 波动率低于阈值时买入跨式
                if hv < OPEN_IV:
                    print(f"[开仓] 买入跨式组合, HV: {hv:.2f}%")
                    position = 1
                    
            elif position == 1:
                # 波动率回归时平仓
                if hv > CLOSE_IV:
                    print(f"[平仓] 波动率回归, HV: {hv:.2f}%")
                    position = 0
    
    api.close()


if __name__ == "__main__":
    main()
