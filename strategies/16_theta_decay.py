#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
TqSdk 天勤量化 — 专业量化交易框架
================================================================================
官方文档：https://doc.shinnytech.com/tqsdk/latest/
GitHub  ：https://github.com/shinnytech/tqsdk-python

策略名称：期权时间价值套利策略
策略编号：16
策略类型：Theta套利
适用品种：金融期权、商品期权
策略日期：2026-03-09
================================================================================

【策略原理】
--------------------
时间价值套利（Theta Trading）是指卖出即将到期的期权，
利用期权时间价值快速衰减的特性获利。

核心思想：
- 卖出剩余时间较短的虚值期权
- 收取权利金，等待期权价值因时间衰减而归零
- 风险有限（权利金为最大收益），但需要严格止损

【策略逻辑】
--------------------
- 选择剩余期限较短（5-15天）的期权
- 卖出虚值看涨或看跌期权
- 持有至期权到期或达到止损条件
- 每日监控Theta decay

【参数说明】
--------------------
  SYMBOL         : 标的期货合约代码
  KLINE_DURATION : K线周期（秒）
  OPTION_TYPE    : 期权类型（call/put）
  DTE_MIN        : 最少剩余交易日
  DTE_MAX        : 最多剩余交易日
  MONEY_RATE     : 虚值程度（实值/虚值）
  MAX_LOSS       : 最大亏损比例

作者：setherffw / tqsdk-options
日期：2026-03-09
================================================================================
"""

from tqsdk import TqApi, TqAuth, TqSim
import numpy as np
from datetime import datetime, timedelta

# ===================== 策略参数 =====================
SYMBOL = "SHFE.rb2505"        # 标的期货（螺纹钢）
KLINE_DURATION = 3600         # 1小时K线
OPTION_TYPE = "put"           # 期权类型：call 或 put
DTE_MIN = 5                   # 最少剩余5天
DTE_MAX = 15                  # 最多剩余15天
MONEY_RATE = 0.95             # 虚值期权：标的价格的95%
MAX_LOSS = 0.03               # 最大亏损3%

# ===================== 辅助函数 =====================
def calculate_theta(spot_price, strike_price, volatility, time_to_expiry, option_type):
    """Theta计算（简化版）"""
    if time_to_expiry <= 0:
        return 0.0
    
    d1 = (np.log(spot_price / strike_price) + (volatility ** 2 / 2) * time_to_expiry) / (volatility * np.sqrt(time_to_expiry))
    d2 = d1 - volatility * np.sqrt(time_to_expiry)
    
    # 简化Theta计算
    theta = - (spot_price * volatility * np.exp(-d1**2/2)) / (2 * np.sqrt(2 * np.pi) * np.sqrt(time_to_expiry))
    
    if option_type == "put":
        theta = theta * 1
    
    return theta / 365  # 转换为每日

def estimate_time_value(spot_price, strike_price, volatility, time_to_expiry):
    """估算期权时间价值"""
    if time_to_expiry <= 0:
        return 0.0
    
    intrinsic = max(0, spot_price - strike_price) if OPTION_TYPE == "call" else max(0, strike_price - spot_price)
    
    # 简化：假设期权价格 = 时间价值 + 内在价值
    time_value = volatility * np.sqrt(time_to_expiry) * spot_price * 0.1
    
    return time_value

# ===================== 主策略 =====================
def main():
    api = TqApi(auth=TqAuth("账号", "密码"), sim=TqSim())
    
    print("=" * 60)
    print("启动：期权时间价值套利策略")
    print(f"标的期货：{SYMBOL}")
    print(f"期权类型：{OPTION_TYPE}")
    print(f"剩余天数：{DTE_MIN}-{DTE_MAX}天")
    print("=" * 60)
    
    # 获取标的行情
    quote = api.get_quote(SYMBOL)
    klines = api.get_kline_serial(SYMBOL, KLINE_DURATION, data_length=30)
    
    position_opened = False
    entry_premium = 0
    strike_price = 0
    
    while True:
        api.wait_update()
        
        if api.is_changing(klines) and not position_opened:
            if len(klines) < 10:
                continue
            
            spot_price = klines['close'][-1]
            
            # 设定行权价（虚值）
            if OPTION_TYPE == "call":
                strike_price = spot_price * MONEY_RATE
            else:
                strike_price = spot_price / MONEY_RATE
            
            # 估算时间价值
            time_value = estimate_time_value(spot_price, strike_price, 0.20, (DTE_MIN + DTE_MAX) / 2 / 365)
            
            print(f"标的现价: {spot_price:.2f}")
            print(f"行权价: {strike_price:.2f}")
            print(f"估算时间价值: {time_value:.2f}")
            
            # 时间价值足够高，开仓卖出期权
            if time_value > spot_price * 0.01:  # 至少1%的价值
                position_opened = True
                entry_premium = time_value
                print(f"开仓卖出{OPTION_TYPE}期权，行权价={strike_price:.2f},权利金={entry_premium:.2f}")
            
        elif position_opened:
            # 监控仓位
            if len(klines) < 10:
                continue
            
            current_price = klines['close'][-1]
            
            # 计算当前损益
            if OPTION_TYPE == "call":
                current_intrinsic = max(0, current_price - strike_price)
            else:
                current_intrinsic = max(0, strike_price - current_price)
            
            current_value = current_intrinsic  # 简化：假设时间价值已衰减
            pnl_pct = (entry_premium - current_value) / entry_premium if entry_premium > 0 else 0
            
            print(f"现价: {current_price:.2f}, 盈亏: {pnl_pct*100:.1f}%")
            
            # 止损条件
            if pnl_pct <= -MAX_LOSS:
                print(f"触及止损，平仓离场")
                break
            
            # 期权到期或价值归零
            if current_value < entry_premium * 0.1:  # 价值衰减90%
                print(f"期权价值大幅衰减，平仓获利")
                break
    
    api.close()
    print("策略结束")

if __name__ == "__main__":
    main()
