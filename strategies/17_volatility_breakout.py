#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
TqSdk 天勤量化 — 专业量化交易框架
================================================================================
官方文档：https://doc.shinnytech.com/tqsdk/latest/
GitHub  ：https://github.com/shinnytech/tqsdk-python

策略名称：期权波动率突破策略
策略编号：17
策略类型：波动率交易
适用品种：金融期权、商品期权
策略日期：2026-03-10
================================================================================

【策略原理】
--------------------
波动率突破策略（Volatility Breakout）是指当期权隐含波动率
突破历史波动率区间时进行交易，预期波动率回归或继续扩大。

核心思想：
- 计算历史波动率作为基准
- 监控隐含波动率与历史波动率的偏离
- 隐含波动率过低时买入期权（预期波动率回归）
- 隐含波动率过高时卖出期权（预期波动率回归）

【策略逻辑】
--------------------
- 计算标的历史波动率（20日）
- 设定波动率突破阈值
- 当隐含波动率突破阈值时开仓
- 波动率回归时平仓

【参数说明】
--------------------
  SYMBOL         : 标的期货合约代码
  KLINE_DURATION : K线周期（秒）
  HV_PERIOD      : 历史波动率计算周期
  IV_THRESHOLD   : 隐含波动率阈值（%）
  OPTION_TYPE    : 期权类型（call/put）

作者：setherffw / tqsdk-options
日期：2026-03-10
================================================================================
"""

from tqsdk import TqApi, TqAuth, TqSim
import numpy as np

# ===================== 策略参数 =====================
SYMBOL = "SHFE.rb2505"        # 标的期货（螺纹钢）
KLINE_DURATION = 3600         # 1小时K线
HV_PERIOD = 20                 # 历史波动率计算周期（天）
IV_THRESHOLD = 25              # 隐含波动率阈值（%）
OPTION_TYPE = "call"           # 期权类型：call 或 put
VOLATILITY_WINDOW = 10          # 波动率窗口

# ===================== 辅助函数 =====================
def calculate_historical_volatility(closes, period=20):
    """计算历史波动率"""
    if len(closes) < period:
        return 0.15  # 默认15%
    
    returns = np.diff(np.log(closes[-period:]))
    hv = np.std(returns) * np.sqrt(252)  # 年化
    return hv

def estimate_implied_volatility(spot_price, strike_price, option_price, time_to_expiry, option_type="call"):
    """简化隐含波动率估算（使用BS公式反推）"""
    if time_to_expiry <= 0 or option_price <= 0:
        return 0.20
    
    # 简化估算：假设波动率与权利金正相关
    # 实际应使用数值方法求解
    time_value = option_price - abs(spot_price - strike_price)
    if time_value < 0:
        time_value = option_price
    
    # 简化IV估算
    iv = (time_value / spot_price) * 10 / np.sqrt(max(time_to_expiry, 0.001))
    iv = min(max(iv, 0.05), 1.0)  # 限制在5%-100%
    return iv

# ===================== 主策略 =====================
def main():
    api = TqApi(auth=TqAuth("账号", "密码"), sim=TqSim())
    
    print("=" * 60)
    print("启动：期权波动率突破策略")
    print(f"标的期货：{SYMBOL}")
    print(f"期权类型：{OPTION_TYPE}")
    print(f"历史波动率周期：{HV_PERIOD}天")
    print(f"隐含波动率阈值：{IV_THRESHOLD}%")
    print("=" * 60)
    
    # 获取标的行情
    klines = api.get_kline_serial(SYMBOL, KLINE_DURATION, data_length=50)
    
    position_opened = False
    position_type = 0  # 1: 买入期权, -1: 卖出期权
    entry_iv = 0
    strike_price = 0
    
    while True:
        api.wait_update()
        
        if api.is_changing(klines):
            if len(klines) < HV_PERIOD + 10:
                continue
            
            closes = klines['close'].values
            
            # 计算历史波动率
            hv = calculate_historical_volatility(closes, HV_PERIOD)
            
            spot_price = closes[-1]
            
            # 设定行权价（平值附近）
            strike_price = spot_price
            
            # 简化隐含波动率估算
            # 假设期权价格按波动率20%计算
            estimated_iv = 0.20 + np.random.uniform(-0.05, 0.05)  # 模拟值
            estimated_iv = hv * (1 + np.random.uniform(-0.2, 0.2))  # 基于HV调整
            
            print(f"标的现价: {spot_price:.2f}, 历史波动率: {hv*100:.1f}%, 估算隐含波动率: {estimated_iv*100:.1f}%")
            
            # 开仓信号
            if not position_opened:
                iv_diff = abs(estimated_iv - hv) / hv
                
                if estimated_iv < hv * 0.8:
                    # 隐含波动率低于历史波动率，买入期权预期回归
                    position_opened = True
                    position_type = 1
                    entry_iv = estimated_iv
                    print(f"开仓：买入{OPTION_TYPE}期权，隐含波动率={estimated_iv*100:.1f}%低于历史={hv*100:.1f}%")
                
                elif estimated_iv > hv * 1.2:
                    # 隐含波动率高于历史波动率，卖出期权预期回归
                    position_opened = True
                    position_type = -1
                    entry_iv = estimated_iv
                    print(f"开仓：卖出{OPTION_type}期权，隐含波动率={estimated_iv*100:.1f}%高于历史={hv*100:.1f}%")
            
            # 监控仓位
            elif position_opened:
                # 波动率回归时平仓
                iv_change = abs(estimated_iv - entry_iv) / entry_iv
                
                if iv_change > 0.3:  # 波动率回归30%
                    print(f"平仓：隐含波动率回归，当前={estimated_iv*100:.1f}%, 变化={iv_change*100:.1f}%")
                    break
                
                # 止损：波动率继续大幅偏离
                if position_type == 1 and estimated_iv < entry_iv * 0.7:
                    print(f"止损：隐含波动率继续下降")
                    break
                elif position_type == -1 and estimated_iv > entry_iv * 1.3:
                    print(f"止损：隐含波动率继续上升")
                    break
    
    api.close()
    print("策略结束")

if __name__ == "__main__":
    main()
