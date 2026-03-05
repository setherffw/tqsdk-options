#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略09 - 看跌期权比率价差策略
原理：
    卖出较高执行价格的看跌期权，买入较低执行价格的看跌期权，
    收取净权利金，在温和下跌行情中获利。

参数：
    - 标的合约：SHFE.rb2505
    - 周期：日线
    - 执行价间距：200点
    - 合约月份：2505
    - 价差比例：1:2

适用行情：温和下跌或震荡偏弱
作者：setherffw / tqsdk-options
"""

from tqsdk import TqApi, TqAuth

# ============ 参数配置 ============
SYMBOL = "SHFE.rb2505"          # 螺纹钢标的
KLINE_DURATION = 24 * 60 * 60  # 日线
STRIKE_LOW = 3200              # 低执行价
STRIKE_HIGH = 3400            # 高执行价格
OPTION_MONTH = "2505"          # 期权月份

# ============ 主策略 ============
def main():
    api = TqApi(auth=TqAuth("账号", "密码"))
    
    print("启动：看跌期权比率价差策略")
    
    quote = api.get_quote(SYMBOL)
    
    # 获取期权合约代码
    put_low = f"SHFE.RB2505P{STRIKE_LOW}"
    put_high = f"SHFE.RB2505P{STRIKE_HIGH}"
    
    put_low_quote = api.get_quote(put_low)
    put_high_quote = api.get_quote(put_high)
    
    position = 0  # 0: 空仓, 1: 持有价差
    
    while True:
        api.wait_update()
        
        if api.is_changing(quote):
            current_price = quote.last_price
            
            if put_low_quote.last_price > 0 and put_high_quote.last_price > 0:
                # 计算价差（卖出2份高价看跌，买入1份低价看跌）
                net_credit = put_high_quote.last_price * 2 - put_low_quote.last_price
                
                print(f"标的: {current_price}, 低执行价期权: {put_low_quote.last_price}, 高执行价期权: {put_high_quote.last_price}")
                print(f"净权利金: {net_credit:.2f}")
                
                # 开仓条件
                if position == 0 and current_price > STRIKE_HIGH + 100:
                    position = 1
                    print(f"[开仓] 卖出比率价差，收取权利金 {net_credit:.2f}")
                
                # 平仓条件
                elif position == 1 and current_price < STRIKE_LOW - 100:
                    position = 0
                    print(f"[平仓] 价格跌破低执行价，平仓了结")
    
    api.close()

if __name__ == "__main__":
    main()
