#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略10 - 风险逆转策略
原理：
    买入看涨期权同时卖出看跌期权，创建类似期货多头但下行风险有限的仓位。
    适用于看涨但不希望承担期货追保风险的投资者。

参数：
    - 标的合约：SHFE.rb2505
    - 周期：日线
    - 执行价：ATM
    - 合约月份：2505

适用行情：温和上涨
作者：setherffw / tqsdk-options
"""

from tqsdk import TqApi, TqAuth

# ============ 参数配置 ============
SYMBOL = "SHFE.rb2505"          # 螺纹钢标的
KLINE_DURATION = 24 * 60 * 60  # 日线
OPTION_MONTH = "2505"          # 期权月份

# ============ 主策略 ============
def main():
    api = TqApi(auth=TqAuth("账号", "密码"))
    
    print("启动：风险逆转策略（Collar）")
    
    quote = api.get_quote(SYMBOL)
    
    # 获取ATM执行价（假设为3500，实际应根据现货价调整）
    ATM_STRIKE = 3500
    
    call_option = f"SHFE.RB{OPTION_MONTH}C{ATM_STRIKE}"
    put_option = f"SHFE.RB{OPTION_MONTH}P{ATM_STRIKE}"
    
    call_quote = api.get_quote(call_option)
    put_quote = api.get_quote(put_option)
    
    position = 0  # 0: 空仓, 1: 持有风险逆转
    
    while True:
        api.wait_update()
        
        if api.is_changing(quote):
            current_price = quote.last_price
            
            if call_quote.last_price > 0 and put_quote.last_price > 0:
                # 计算净成本
                net_debit = call_quote.last_price - put_quote.last_price
                
                print(f"标的: {current_price}, 看涨: {call_quote.last_price}, 看跌: {put_quote.last_price}")
                print(f"净成本: {net_debit:.2f}")
                
                # 开仓条件：隐含波动率偏低且预期上涨
                if position == 0 and net_debit < 50:
                    position = 1
                    print(f"[开仓] 买入看涨+卖出看跌，净成本 {net_debit:.2f}")
                
                # 平仓条件：价格跌破执行价一定幅度
                elif position == 1 and current_price < ATM_STRIKE - 200:
                    position = 0
                    print(f"[平仓] 价格跌破支撑位，平仓了结")
    
    api.close()

if __name__ == "__main__":
    main()
