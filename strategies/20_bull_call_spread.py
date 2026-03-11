#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
TqSdk 天勤量化 — 专业量化交易框架
================================================================================
官方文档：https://doc.shinnytech.com/tqsdk/latest/
GitHub  ：https://github.com/shinnytech/tqsdk-python

策略名称：期权牛市价差策略
策略编号：20
策略类型：期权价差策略
适用品种：金融期权、商品期权
策略日期：2026-03-11
================================================================================

【策略原理】
--------------------
牛市价差策略（Bull Call Spread）是指在预期标的价格温和上涨时，
同时买入一个看涨期权并卖出一个更高行权价的看涨期权。
该策略收益有限、风险有限，适合震荡上行行情。

核心思想：
- 买入低行权价看涨期权（成本）
- 卖出高行权价看涨期权（收入）
- 降低净成本，牺牲上方收益空间
- 标的价格小幅上涨即可盈利

【策略逻辑】
--------------------
- 买入平值或虚值看涨期权
- 卖出更高行权价的虚值看涨期权
- 设定目标价位，到价止盈
- 设定止损，行情不利时平仓

【参数说明】
--------------------
  SYMBOL         : 标的期货合约代码
  KLINE_DURATION : K线周期（秒）
  LOW_STRIKE     : 买入看涨期权的行权价比例
  HIGH_STRIKE    : 卖出看涨期权的行权价比例
  EXPIRY_DAYS    : 期权到期天数

作者：setherffw / tqsdk-options
日期：2026-03-11
================================================================================
"""

from tqsdk import TqApi, TqAuth, TqSim
import numpy as np

# ===================== 策略参数 =====================
SYMBOL = "SHFE.rb2505"        # 标的期货（螺纹钢）
KLINE_DURATION = 3600         # 1小时K线
LOW_STRIKE_PCT = 1.00        # 买入看涨期权行权价（平值）
HIGH_STRIKE_PCT = 1.10       # 卖出看涨期权行权价（虚值10%）
EXPIRY_DAYS = 30              # 期权到期天数
TARGET_PROFIT = 0.50          # 目标收益率50%
STOP_LOSS = -0.30             # 止损收益率-30%

# ===================== 辅助函数 =====================
def calculate_call_price(spot, strike, time_to_expiry, volatility=0.2, risk_free=0.03):
    """简化看涨期权定价"""
    if time_to_expiry <= 0:
        return max(0, strike - spot)
    
    moneyness = (spot - strike) / spot
    time_value = volatility * np.sqrt(time_to_expiry) * spot * 0.3
    intrinsic = max(0, strike - spot)
    
    return intrinsic + time_value * max(0, 1 - abs(moneyness))

def calculate_bull_spread_pnl(spot, low_strike, high_strike, low_premium, high_premium):
    """计算牛市价差组合盈亏"""
    # 买入看涨期权到期价值
    long_call_value = max(0, spot - low_strike)
    # 卖出看涨期权到期价值
    short_call_value = max(0, spot - high_strike)
    
    # 净权利金（收入-支出）
    net_premium = high_premium - low_premium
    
    # 到期收益
    pnl = (long_call_value - short_call_value) - net_premium
    
    return pnl, net_premium

# ===================== 主策略 =====================
def main():
    api = TqApi(auth=TqAuth("账号", "密码"), sim=TqSim())
    
    print("=" * 60)
    print("启动：牛市价差期权策略")
    print(f"标的期货：{SYMBOL}")
    print(f"买入行权价：{LOW_STRIKE_PCT*100}%")
    print(f"卖出行权价：{HIGH_STRIKE_PCT*100}%")
    print(f"期权到期天数：{EXPIRY_DAYS}天")
    print("=" * 60)
    
    # 获取标的行情
    klines = api.get_kline_serial(SYMBOL, KLINE_DURATION, data_length=50)
    
    position_opened = False
    low_strike = 0
    high_strike = 0
    low_premium = 0
    high_premium = 0
    entry_spot = 0
    
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
                low_strike = current_spot * LOW_STRIKE_PCT
                high_strike = current_spot * HIGH_STRIKE_PCT
                
                # 估算期权价格
                time_to_expiry = EXPIRY_DAYS / 252
                low_premium = calculate_call_price(current_spot, low_strike, time_to_expiry)
                high_premium = calculate_call_price(current_spot, high_strike, time_to_expiry)
                
                entry_spot = current_spot
                position_opened = True
                
                net_premium = high_premium - low_premium
                max_profit = (high_strike - low_strike) - net_premium
                max_loss = net_premium
                
                print(f"开仓：买入看涨@{low_strike:.2f}，卖出看涨@{high_strike:.2f}")
                print(f"净权利金：{net_premium:.2f}")
                print(f"最大盈利：{max_profit:.2f}，最大亏损：{max_loss:.2f}")
            
            # 监控仓位
            elif position_opened:
                pnl, net_premium = calculate_bull_spread_pnl(
                    current_spot, low_strike, high_strike, low_premium, high_premium
                )
                
                pnl_pct = pnl / net_premium if net_premium > 0 else 0
                
                print(f"现价: {current_spot:.2f}, 盈亏: {pnl:.2f} ({pnl_pct*100:.1f}%)")
                
                # 止盈
                if pnl_pct >= TARGET_PROFIT:
                    print(f"止盈：收益达{TARGET_PROFIT*100}%")
                    break
                
                # 止损
                if pnl_pct <= STOP_LOSS:
                    print(f"止损：亏损达{abs(STOP_LOSS)*100}%")
                    break
    
    api.close()
    print("策略结束")

if __name__ == "__main__":
    main()
