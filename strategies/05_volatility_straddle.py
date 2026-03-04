#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略05 - 波动率套利：跨式组合做多波动率策略
原理：
    当预期市场将出现大幅波动但不确定方向时，
    买入跨式组合（Call + Put）做多波动率。
    波动率上升时平仓获利。

参数：
    - 标的合约：SHFE.rb2505
    - 期权到期日：2025-06-15
    - 行权价：ATM
    - 波动率阈值：开仓波动率 15%，平仓波动率 25%

适用行情：预期重大事件前（如非农、利率决议）
作者：setherffw / tqsdk-options
"""

from tqsdk import TqApi, TqAuth, TqOption
import numpy as np

# ============ 参数配置 ============
UNDERLYING = "SHFE.rb2505"      # 标的合约
EXPIRY_DATE = "20250516"       # 到期日
STRIKE_OFFSET = 0              # ATM: 0
VOL_OPEN = 15                  # 开仓波动率阈值(%)
VOL_CLOSE = 25                 # 平仓波动率阈值(%)
LOT_SIZE = 1                   # 手数

# ============ 主策略 ============
def main():
    api = TqApi(auth=TqAuth("账号", "密码"))
    
    print("启动：波动率套利策略")
    
    underlying_quote = api.get_quote(UNDERLYING)
    underlying_price = underlying_quote.last_price
    
    # 获取ATM期权
    option_api = TqOption(underlying_symbol=UNDERLYING)
    call_symbol = option_api.get_option_symbol(UNDERLYING, EXPIRY_DATE, 
                                                underlying_price, "C")
    put_symbol = option_api.get_option_symbol(UNDERLYING, EXPIRY_DATE, 
                                               underlying_price, "P")
    
    print(f"标的: {UNDERLYING}, 价格: {underlying_price}")
    print(f"Call: {call_symbol}, Put: {put_symbol}")
    
    call_quote = api.get_quote(call_symbol)
    put_quote = api.get_quote(put_symbol)
    
    position = 0
    
    while True:
        api.wait_update()
        
        if api.is_changing(call_quote) or api.is_changing(put_quote):
            call_price = call_quote.last_price
            put_price = put_quote.last_price
            
            # 简化计算：隐含波动率
            total_premium = call_price + put_price
            
            print(f"Call: {call_price}, Put: {put_price}, 总权利金: {total_premium:.2f}")
            
            # 无持仓时开仓
            if position == 0 and underlying_price > 0:
                print(f"[开仓] 买入跨式组合")
                position = 1
                
            # 波动率上升时平仓（简化判断：权利金上涨 30%）
            elif position == 1:
                if total_premium > call_price + put_price * 1.3:
                    print(f"[平仓] 波动率上升，平仓获利")
                    position = 0
    
    api.close()

if __name__ == "__main__":
    main()
