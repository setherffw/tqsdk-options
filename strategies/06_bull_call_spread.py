#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略06 - 垂直价差：牛市价差组合策略
原理：
    预期标的价格温和上涨时，使用垂直价差策略。
    买入低行权价Call，卖出高行权价Call。
    风险有限，收益有限。

参数：
    - 标的合约：SHFE.rb2505
    - 低行权价：ATM
    - 高行权价：ATM + 200
    - 到期日：2025-06-15

适用行情：预期标的价格小幅上涨
作者：setherffw / tqsdk-options
"""

from tqsdk import TqApi, TqAuth, TqOption
import numpy as np

# ============ 参数配置 ============
UNDERLYING = "SHFE.rb2505"      # 标的合约
EXPIRY_DATE = "20250516"        # 到期日
STRIKE_LOW = 0                  # 低行权价偏移
STRIKE_HIGH = 200               # 高行权价偏移
LOT_SIZE = 1                    # 手数
PROFIT_TARGET = 100             # 止盈点数
STOP_LOSS = 50                  # 止损点数

# ============ 主策略 ============
def main():
    api = TqApi(auth=TqAuth("账号", "密码"))
    
    print("启动：牛市价差策略")
    
    underlying_quote = api.get_quote(UNDERLYING)
    underlying_price = underlying_quote.last_price
    
    option_api = TqOption(underlying_symbol=UNDERLYING)
    
    # 获取看涨价差
    call_low = option_api.get_option_symbol(UNDERLYING, EXPIRY_DATE, 
                                              underlying_price + STRIKE_LOW, "C")
    call_high = option_api.get_option_symbol(UNDERLYING, EXPIRY_DATE, 
                                               underlying_price + STRIKE_HIGH, "C")
    
    print(f"标的: {UNDERLYING}, 价格: {underlying_price}")
    print(f"买入: {call_low}, 卖出: {call_high}")
    
    call_low_quote = api.get_quote(call_low)
    call_high_quote = api.get_quote(call_high)
    
    entry_spread = 0
    position = 0
    
    while True:
        api.wait_update()
        
        if api.is_changing(call_low_quote) or api.is_changing(call_high_quote):
            call_low_price = call_low_quote.last_price
            call_high_price = call_high_quote.last_price
            
            spread = call_low_price - call_high_price  # 价差 = 买低卖高
            
            if position == 0 and call_low_price > 0 and call_high_price > 0:
                entry_spread = spread
                print(f"[开仓] 价差: {spread:.2f}")
                position = 1
                
            elif position == 1:
                pnl = spread - entry_spread
                print(f"当前价差: {spread:.2f}, 盈亏: {pnl:.2f}")
                
                if pnl > PROFIT_TARGET:
                    print(f"[止盈] 获利: {pnl:.2f}")
                    position = 0
                elif pnl < -STOP_LOSS:
                    print(f"[止损] 亏损: {pnl:.2f}")
                    position = 0
    
    api.close()

if __name__ == "__main__":
    main()
