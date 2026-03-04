#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略07 - 波动率交易：波动率价差策略
原理：
    波动率交易的核心是低买高卖波动率。
    当隐含波动率偏低时买入跨式组合，高时卖出。

参数：
    - 标的合约：SHFE.rb2505
    - 到期日：2025-05-16
    - 行权价：ATM
    - 手数：各1手

适用行情：预期波动率将发生变化
作者：setherffw / tqsdk-options
"""

from tqsdk import TqApi, TqAuth, TqOption
import numpy as np

# ============ 参数配置 ============
UNDERLYING = "SHFE.rb2505"      # 标的合约
EXPIRY_DATE = "20250516"        # 到期日
LOT_SIZE = 1                    # 手数
VOL_LOW = 15                    # 波动率偏低阈值
VOL_HIGH = 30                   # 波动率偏高阈值

# ============ 主策略 ============
def main():
    api = TqApi(auth=TqAuth("账号", "密码"))
    
    print("启动：波动率价差策略")
    
    underlying_quote = api.get_quote(UNDERLYING)
    underlying_price = underlying_quote.last_price
    
    option_api = TqOption(underlying_symbol=UNDERLYING)
    
    # 获取ATM期权
    call_symbol = option_api.get_option_symbol(UNDERLYING, EXPIRY_DATE, 
                                                  underlying_price, "C")
    put_symbol = option_api.get_option_symbol(UNDERLYING, EXPIRY_DATE, 
                                                 underlying_price, "P")
    
    print(f"标的: {UNDERLYING}, 价格: {underlying_price}")
    print(f"买入Call: {call_symbol}, 买入Put: {put_symbol}")
    
    call_quote = api.get_quote(call_symbol)
    put_quote = api.get_quote(put_symbol)
    
    position = 0
    entry_cost = 0
    
    while True:
        api.wait_update()
        
        if api.is_changing(call_quote) or api.is_changing(put_quote):
            call_price = call_quote.last_price
            put_price = put_quote.last_price
            
            if call_price <= 0 or put_price <= 0:
                continue
                
            total_cost = call_price + put_price  # 跨式组合成本
            
            # 简单波动率估算（实际应使用模型）
            implied_vol = total_cost / underlying_price * 100
            
            print(f"Call: {call_price:.2f}, Put: {put_price:.2f}, 总成本: {total_cost:.2f}")
            
            if position == 0:
                if implied_vol < VOL_LOW:
                    entry_cost = total_cost
                    position = 1
                    print(f"[开仓] 买入波动率, IV: {implied_vol:.1f}%")
                elif implied_vol > VOL_HIGH:
                    entry_cost = total_cost
                    position = -1
                    print(f"[开仓] 卖出波动率, IV: {implied_vol:.1f}%")
                    
            elif position == 1:
                pnl = entry_cost - total_cost
                print(f"[持有] 盈亏: {pnl:.2f}")
                # 波动率回归时平仓
                if implied_vol > 20:
                    print(f"[平仓] 波动率回归")
                    position = 0
                    
            elif position == -1:
                pnl = total_cost - entry_cost
                print(f"[持有] 盈亏: {pnl:.2f}")
                # 波动率回归时平仓
                if implied_vol < 25:
                    print(f"[平仓] 波动率回归")
                    position = 0
    
    api.close()

if __name__ == "__main__":
    main()
