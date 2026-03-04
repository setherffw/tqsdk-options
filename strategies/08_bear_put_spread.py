#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略08 - 垂直价差：熊市价差组合策略
原理：
    预期标的价格下跌时，使用熊市价差策略。
    买入高行权价Put，卖出低行权价Put。
    风险有限，收益有限。

参数：
    - 标的合约：SHFE.rb2505
    - 低行权价：ATM - 200
    - 高行权价：ATM
    - 到期日：2025-05-16
    - 止盈止损：50/30点

适用行情：预期标的价格小幅下跌
作者：setherffw / tqsdk-options
"""

from tqsdk import TqApi, TqAuth, TqOption
import numpy as np

# ============ 参数配置 ============
UNDERLYING = "SHFE.rb2505"      # 标的合约
EXPIRY_DATE = "20250516"        # 到期日
STRIKE_LOW = -200               # 低行权价偏移
STRIKE_HIGH = 0                 # 高行权价偏移
LOT_SIZE = 1                    # 手数
PROFIT_TARGET = 50              # 止盈点数
STOP_LOSS = 30                  # 止损点数

# ============ 主策略 ============
def main():
    api = TqApi(auth=TqAuth("账号", "密码"))
    
    print("启动：熊市价差策略")
    
    underlying_quote = api.get_quote(UNDERLYING)
    underlying_price = underlying_quote.last_price
    
    option_api = TqOption(underlying_symbol=UNDERLYING)
    
    # 获取看跌价差
    put_low = option_api.get_option_symbol(UNDERLYING, EXPIRY_DATE, 
                                             underlying_price + STRIKE_LOW, "P")
    put_high = option_api.get_option_symbol(UNDERLYING, EXPIRY_DATE, 
                                              underlying_price + STRIKE_HIGH, "P")
    
    print(f"标的: {UNDERLYING}, 价格: {underlying_price}")
    print(f"买入: {put_low}, 卖出: {put_high}")
    
    put_low_quote = api.get_quote(put_low)
    put_high_quote = api.get_quote(put_high)
    
    entry_spread = 0
    position = 0
    
    while True:
        api.wait_update()
        
        if api.is_changing(put_low_quote) or api.is_changing(put_high_quote):
            put_low_price = put_low_quote.last_price
            put_high_price = put_high_quote.last_price
            
            # 价差 = 买高卖低
            spread = put_high_price - put_low_price
            
            if position == 0 and put_low_price > 0 and put_high_price > 0:
                entry_spread = spread
                print(f"[开仓] 价差: {spread:.2f}")
                position = 1
                
            elif position == 1:
                pnl = entry_spread - spread
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
