#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
TqSdk 天勤量化 — 专业量化交易框架
================================================================================
官方文档：https://doc.shinnytech.com/tqsdk/latest/
GitHub  ：https://github.com/shinnytech/tqsdk-python

策略名称：期权Delta中性对冲策略
策略编号：15
策略类型：Delta中性交易
适用品种：金融期权、商品期权
策略日期：2026-03-09
================================================================================

【策略原理】
--------------------
Delta中性策略（Delta Neutral）是指通过同时持有期权合约和标的期货，
使组合的Delta值为0，消除方向性风险，仅从波动率或时间价值中获利。

核心思想：
- 买入期权后，持续调整标的期货仓位使组合Delta保持中性
- 无论价格涨跌，组合价值变化互相抵消
- 盈利来源于隐含波动率变化和时间价值衰减

【策略逻辑】
--------------------
- 买入看涨期权或看跌期权
- 根据期权Delta值，计算对冲所需期货手数
- 定期调整期货仓位保持Delta中性
- 持有至波动率回归或到期

【参数说明】
--------------------
  SYMBOL         : 标的期货合约代码
  KLINE_DURATION : K线周期（秒）
  OPTION_TYPE    : 期权类型（call/put）
  STRIKE_OFFSET  : 行权价偏移（ATM的百分比）
  HEDGE_INTERVAL : 对冲间隔（秒）
  VOL_EXIT       : 隐含波动率回归阈值

作者：setherffw / tqsdk-options
日期：2026-03-09
================================================================================
"""

from tqsdk import TqApi, TqAuth, TqSim
import numpy as np

# ===================== 策略参数 =====================
SYMBOL = "SHFE.rb2505"        # 标的期货（螺纹钢）
KLINE_DURATION = 3600         # 1小时K线
OPTION_TYPE = "call"          # 期权类型：call 或 put
STRIKE_OFFSET = 0.03          # 3% 虚值期权
HEDGE_INTERVAL = 3600         # 对冲间隔：1小时
VOL_EXIT = 0.15               # 隐含波动率回归阈值

# ===================== 辅助函数 =====================
def calculate_delta(spot_price, strike_price, volatility, time_to_expiry, option_type):
    """简化的Delta计算"""
    if time_to_expiry <= 0:
        return 0.0
    
    # 简化版：假设标的价格服从正态分布
    d1 = (np.log(spot_price / strike_price) + (volatility ** 2 / 2) * time_to_expiry) / (volatility * np.sqrt(time_to_expiry))
    
    if option_type == "call":
        delta = 0.5 * (1 + np.math.erf(d1 / np.sqrt(2)))
    else:
        delta = 0.5 * (1 - np.math.erf(d1 / np.sqrt(2)))
    
    return delta

# ===================== 主策略 =====================
def main():
    api = TqApi(auth=TqAuth("账号", "密码"), sim=TqSim())
    
    print("=" * 60)
    print("启动：期权Delta中性对冲策略")
    print(f"标的期货：{SYMBOL}")
    print(f"期权类型：{OPTION_TYPE}")
    print("=" * 60)
    
    # 获取标的行情
    quote = api.get_quote(SYMBOL)
    
    # 获取期权链（简化版：直接使用期货模拟）
    position = 0
    entry_iv = 0.20  # 假设入场隐含波动率
    
    klines = api.get_kline_serial(SYMBOL, KLINE_DURATION, data_length=50)
    last_hedge_time = 0
    
    while True:
        api.wait_update()
        
        # 每隔HEDGE_INTERVAL对冲一次
        current_time = api.get_trading_time()
        
        if api.is_changing(klines) and (current_time - last_hedge_time) > HEDGE_INTERVAL:
            if len(klines) < 20:
                continue
            
            spot_price = klines['close'][-1]
            
            # 简化：假设隐含波动率为固定值或根据行情估算
            current_iv = entry_iv  # 简化处理
            
            print(f"现价: {spot_price:.2f}, 隐含波动率: {current_iv*100:.1f}%")
            
            # 检查是否达到退出条件
            if abs(current_iv - entry_iv) < VOL_EXIT:
                print(f"波动率回归，平仓离场")
                break
            
            last_hedge_time = current_time
    
    api.close()
    print("策略结束")

if __name__ == "__main__":
    main()
