#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
TqSdk 天勤量化 — 专业量化交易框架
================================================================================
官方文档：https://doc.shinnytech.com/tqsdk/latest/
GitHub  ：https://github.com/shinnytech/tqsdk-python

策略名称：期权保护性看跌策略
策略编号：19
策略类型：期权保险策略
适用品种：金融期权、商品期权
策略日期：2026-03-11
================================================================================

【策略原理】
--------------------
保护性看跌策略（Protective Put）是指在持有标的期货多头的同时，
买入看跌期权进行下行保护。当标的价格下跌时，看跌期权的收益
可以抵消部分损失；当标的价格上涨时，期货多头收益不受限制。

核心思想：
- 持有标的期货多头作为主要收益来源
- 买入看跌期权作为保险，对冲下行风险
- 有限的下行风险换取无限的上涨空间

【策略逻辑】
--------------------
- 持有标的期货多头仓位
- 买入虚值看跌期权作为保护
- 设定止损线，当期货亏损超过一定比例时期权对冲生效

【参数说明】
--------------------
  SYMBOL         : 标的期货合约代码
  KLINE_DURATION : K线周期（秒）
  PUT_STRIKE     : 看跌期权行权价（虚值程度）
  EXPIRY_DAYS    : 期权到期天数
  STOP_LOSS      : 期货止损比例

作者：setherffw / tqsdk-options
日期：2026-03-11
================================================================================
"""

from tqsdk import TqApi, TqAuth, TqSim
import numpy as np

# ===================== 策略参数 =====================
SYMBOL = "SHFE.rb2505"        # 标的期货（螺纹钢）
KLINE_DURATION = 3600         # 1小时K线
PUT_STRIKE_PCT = 0.95         # 看跌期权虚值程度（95%为虚值）
EXPIRY_DAYS = 30               # 期权到期天数
STOP_LOSS = 0.03              # 期货止损3%
TAKE_PROFIT = 0.05            # 期货止盈5%

# ===================== 辅助函数 =====================
def calculate_option_price(spot, strike, time_to_expiry, volatility=0.2, risk_free=0.03, option_type="put"):
    """简化期权定价（使用BS公式思想）"""
    if time_to_expiry <= 0:
        return max(0, spot - strike) if option_type == "put" else max(0, strike - spot)
    
    # 简化计算
    moneyness = abs(spot - strike) / spot
    time_value = volatility * np.sqrt(time_to_expiry) * spot * 0.3
    intrinsic = max(0, spot - strike) if option_type == "put" else max(0, strike - spot)
    
    return intrinsic + time_value * (1 - moneyness)

def calculate_profit_loss(spot, entry_spot, position_type, put_cost, put_strike):
    """计算组合盈亏"""
    # 期货盈亏
    future_pnl = (spot - entry_spot) / entry_spot if position_type == 1 else (entry_spot - spot) / entry_spot
    
    # 看跌期权盈亏
    put_value = calculate_option_price(spot, put_strike, EXPIRY_DAYS/252, option_type="put")
    put_pnl = (put_value - put_cost) / put_cost if put_cost > 0 else 0
    
    return future_pnl, put_pnl

# ===================== 主策略 =====================
def main():
    api = TqApi(auth=TqAuth("账号", "密码"), sim=TqSim())
    
    print("=" * 60)
    print("启动：保护性看跌期权策略")
    print(f"标的期货：{SYMBOL}")
    print(f"看跌期权虚值程度：{PUT_STRIKE_PCT*100}%")
    print(f"期权到期天数：{EXPIRY_DAYS}天")
    print(f"期货止损：{STOP_LOSS*100}%")
    print("=" * 60)
    
    # 获取标的行情
    klines = api.get_kline_serial(SYMBOL, KLINE_DURATION, data_length=50)
    
    position_opened = False
    entry_spot = 0
    put_strike = 0
    put_cost = 0
    
    while True:
        api.wait_update()
        
        if api.is_changing(klines):
            if len(klines) < 10:
                continue
            
            closes = klines['close'].values
            current_spot = closes[-1]
            
            # 首次开仓
            if not position_opened:
                # 设定行权价
                put_strike = current_spot * PUT_STRIKE_PCT
                
                # 估算看跌期权价格
                put_cost = calculate_option_price(current_spot, put_strike, EXPIRY_DAYS/252, option_type="put")
                
                entry_spot = current_spot
                position_opened = True
                
                print(f"开仓：买入期货多头@{entry_spot:.2f}，买入看跌期权@{put_strike:.2f}，权利金≈{put_cost:.2f}")
                print(f"组合最大亏损：{((entry_spot - put_strike)/entry_spot - put_cost/entry_spot)*100:.2f}%")
            
            # 监控仓位
            elif position_opened:
                future_pnl, put_pnl = calculate_profit_loss(current_spot, entry_spot, 1, put_cost, put_strike)
                total_pnl = future_pnl + put_pnl * (put_cost / entry_spot)
                
                print(f"现价: {current_spot:.2f}, 期货盈亏: {future_pnl*100:.2f}%, 期权盈亏: {put_pnl*100:.2f}%, 总盈亏: {total_pnl*100:.2f}%")
                
                # 止损
                if future_pnl <= -STOP_LOSS:
                    print(f"止损：期货亏损达{STOP_LOSS*100}%，期权保护生效")
                    break
                
                # 止盈
                if future_pnl >= TAKE_PROFIT:
                    print(f"止盈：期货盈利达{TAKE_PROFIT*100}%")
                    break
    
    api.close()
    print("策略结束")

if __name__ == "__main__":
    main()
