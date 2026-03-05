#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略12 - 备兑看涨期权策略（Covered Call）
原理：
    持有标的期货多头，同时卖出虚值看涨期权
    收取权利金，降低持仓成本

参数：
    - 标的合约：SHFE.rb2505
    - 虚值看涨期权：M2405C3800
    - 标的周期：日线
    - 期权周期：日线
    - 行权价偏移：3%

适用行情：震荡或小幅上涨行情
作者：setherffw / tqsdk-options
"""

from tqsdk import TqApi, TqAuth, TqSim, TargetPosTask

# ============ 参数配置 ============
UNDERLYING = "SHFE.rb2505"       # 标的期货
CALL_SYMBOL = "M2405C3800"      # 虚值看涨期权
KLINE_DURATION = 24 * 60 * 60   # 日线
STRIKE_OFFSET = 0.03            # 行权价偏移3%
VOLUME = 1                       # 交易组数


def main():
    api = TqApi(account=TqSim(), auth=TqAuth("账号", "密码"))
    print("启动：备兑看涨期权策略")
    
    underlying = api.get_quote(UNDERLYING)
    call_opt = api.get_quote(CALL_SYMBOL)
    
    target_pos = TargetPosTask(api, UNDERLYING)
    
    # 持有标的期货多头
    target_pos.set_target_volume(VOLUME)
    
    position = 1  # 持有标的
    
    while True:
        api.wait_update()
        
        if api.is_changing(underlying):
            underlying_price = underlying.last_price
            call_price = call_opt.last_price
            
            print(f"标的: {underlying_price}, 认购: {call_price:.2f}")
            
            # 到期时如果期权被行权，平掉标的仓位
            if call_opt.expire_date and call_opt.expire_date <= api.get_trading_date():
                print(f"[期权到期] 平掉标的仓位")
                target_pos.set_target_volume(0)
                position = 0
    
    api.close()


if __name__ == "__main__":
    main()
