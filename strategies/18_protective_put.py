#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
TqSdk 天勤量化 — 专业量化交易框架
================================================================================
官方文档：https://doc.shinnytech.com/tqsdk/latest/
GitHub  ：https://github.com/shinnytech/tqsdk-python

策略名称：期权保护性看跌策略
策略编号：18
策略类型：保险策略
适用品种：金融期权、商品期权
策略日期：2026-03-10
================================================================================

【策略原理】
--------------------
保护性看跌期权（Protective Put）是指持有标的期货多头的同时，
买入看跌期权作为保险，限制下行风险。

核心思想：
- 持有标的期货多头仓位
- 买入看跌期权对冲下行风险
- 保留上行盈利空间
- 支付权利金获取保护

【策略逻辑】
--------------------
- 持有标的期货多头
- 买入虚值看跌期权作为保险
- 定期评估保护效果
- 期货止损时期权对冲损失

【参数说明】
--------------------
  SYMBOL         : 标的期货合约代码
  KLINE_DURATION : K线周期（秒）
  PUT_STRIKE     : 看跌期权行权价比例（虚值程度）
  EXPIRY_DAYS    : 期权剩余天数
  FUTURES_STOP   : 期货止损比例

作者：setherffw / tqsdk-options
日期：2026-03-10
================================================================================
"""

from tqsdk import TqApi, TqAuth, TqSim
import numpy as np

# ===================== 策略参数 =====================
SYMBOL = "SHFE.rb2505"        # 标的期货（螺纹钢）
KLINE_DURATION = 1800         # 30分钟K线
PUT_STRIKE = 0.95             # 虚值程度：标的价格的95%
EXPIRY_DAYS = 30              # 期权剩余天数
FUTURES_STOP = 0.03           # 期货止损3%
MAX_COST = 0.02               # 最大权利金成本2%

# ===================== 辅助函数 =====================
def calculate_put_premium(spot_price, strike_price, volatility, time_to_expiry):
    """估算看跌期权权利金（简化BS公式）"""
    if time_to_expiry <= 0:
        return max(0, strike_price - spot_price)
    
    # 简化估算
    moneyness = strike_price / spot_price
    time_value = volatility * np.sqrt(time_to_expiry) * spot_price * 0.15
    
    if moneyness < 1:  # 虚值
        return time_value * (1 - moneyness)
    else:  # 实值
        intrinsic = strike_price - spot_price
        return intrinsic + time_value * 0.5

# ===================== 主策略 =====================
def main():
    api = TqApi(auth=TqAuth("账号", "密码"), sim=TqSim())
    
    print("=" * 60)
    print("启动：期权保护性看跌策略")
    print(f"标的期货：{SYMBOL}")
    print(f"看跌期权行权价：{PUT_STRIKE*100:.0f}%")
    print(f"期权剩余天数：{EXPIRY_DAYS}天")
    print(f"期货止损：{FUTURES_STOP*100:.0f}%")
    print("=" * 60)
    
    # 获取标的行情
    klines = api.get_kline_serial(SYMBOL, KLINE_DURATION, data_length=50)
    
    position_opened = False
    entry_futures_price = 0
    put_strike = 0
    put_premium = 0
    
    while True:
        api.wait_update()
        
        if api.is_changing(klines):
            if len(klines) < 20:
                continue
            
            closes = klines['close'].values
            spot_price = closes[-1]
            
            # 首次开仓
            if not position_opened:
                # 设定看跌期权行权价
                put_strike = spot_price * PUT_STRIKE
                
                # 估算权利金
                time_to_expiry = EXPIRY_DAYS / 365
                put_premium = calculate_put_premium(spot_price, put_strike, 0.25, time_to_expiry)
                
                # 权利金成本检查
                cost_pct = put_premium / spot_price
                if cost_pct <= MAX_COST:
                    position_opened = True
                    entry_futures_price = spot_price
                    print(f"开仓：期货多头@{spot_price:.2f} + 看跌期权保护@{put_strike:.2f}, 权利金={put_premium:.2f} ({cost_pct*100:.1f}%)")
                else:
                    print(f"权利金成本{cost_pct*100:.1f}%超过限制，等待...")
                    continue
            
            # 持仓监控
            else:
                futures_pnl = (spot_price - entry_futures_price) / entry_futures_price
                put_value = calculate_put_premium(spot_price, put_strike, 0.25, (EXPIRY_DAYS - 1) / 365)
                
                # 计算组合盈亏（期货盈亏 + 期权盈亏）
                put_pnl = (put_premium - put_value) / put_premium if put_premium > 0 else 0
                total_pnl = futures_pnl + put_pnl * (put_premium / spot_price)
                
                print(f"期货现价: {spot_price:.2f}, 期货盈亏: {futures_pnl*100:.1f}%, 期权价值: {put_value:.2f}")
                
                # 期货止损
                if futures_pnl <= -FUTURES_STOP:
                    print(f"期货触及止损@{spot_price:.2f}，期权保护减少损失")
                    print(f"期权剩余价值: {put_value:.2f}")
                    break
                
                # 期权到期
                if EXPIRY_DAYS <= 1:
                    print(f"期权到期，释放保护")
                    break
    
    api.close()
    print("策略结束")

if __name__ == "__main__":
    main()
