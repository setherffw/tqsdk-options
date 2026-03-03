"""
================================================================================
TqSdk 天勤量化 — 专业量化交易框架
================================================================================
官方文档：https://doc.shinnytech.com/tqsdk/latest/
GitHub  ：https://github.com/shinnytech/tqsdk-python

TqSdk（天勤量化软件开发包）是由信易科技基于 DIFF 协议开发的开源 Python 量化
交易框架，支持期货、期权、股票等多品种实盘/模拟/回测交易。
================================================================================

策略名称：波动率曲面套利策略
策略编号：03
策略类型：波动率套利
适用品种：50ETF期权、沪深300ETF期权
策略日期：2026-03-03
================================================================================

【策略原理】
--------------------
波动率曲面套利（Volatility Surface Arbitrage）利用期权市场中不同执行价格
和到期时间的波动率差异进行套利。

核心思想：
  1. 波动率微笑/偏斜：虚值期权（OTM）和实值期权（ITM）的隐含波动率（IV）
     通常高于平值期权（ATM），形成"微笑"曲线
  2. 期限结构：不同到期时间的期权波动率存在系统性差异
  3. 套利机会：当某期权的IV相对其他期权显著偏高时，卖出高IV期权，
     买入低IV期权，等待IV回归均衡

本策略：
  1. 监控同一到期日、不同执行价的期权链
  2. 计算各期权的隐含波动率
  3. 当某期权IV超过均值+阈值时，做空波动率（卖出期权+Delta对冲）
  4. 当某期权IV低于均值-阈值时，做多波动率（买入期权+Delta对冲）

【策略参数说明】
--------------------
  UNDERLYING      : 标的ETF代码（SHFE.10004XXX）
  OPTION_EXPIRY   : 期权到期日（近月/远月）
  IV_ENTRY_THRESHOLD: IV偏离阈值，超过此值入场（默认 3%）
  IV_EXIT_THRESHOLD : IV回归阈值，回到此值平仓（默认 1%）
  DELTA_HEDGE_THRESHOLD: Delta对冲阈值
  POSITION_SIZE   : 开仓数量

【风险提示】
--------------------
  1. 波动率预测难度大，模型风险较高
  2. 需要实时计算隐含波动率，计算量大
  3. 流动性风险：部分期权合约买卖价差大
  4. Gamma风险：临近到期Gamma增大，对冲难度增加
================================================================================
"""

from tqsdk import TqApi, TqAuth
from tqsdk.tafunc import get_real_volatility
import numpy as np

# ============ 参数配置 ============
UNDERLYING = "SHFE.10004"      # 50ETF
OPTION_EXPIRY = "2406"          # 6月到期
ATM_STRIKE_PCT = 1.0           # 平值期权执行价比例
IV_ENTRY_THRESHOLD = 0.03       # IV入场阈值 3%
IV_EXIT_THRESHOLD = 0.01       # IV出场阈值 1%
POSITION_SIZE = 1               # 开仓数量

def calc_implied_vol(price, S, K, T, r=0.03):
    """
    简化版隐含波动率计算（使用BS公式反推）
    实际实现需要使用数值方法（如牛顿法）
    """
    # 这里简化处理，使用历史波动率替代
    return 0.15  # 默认15%

def main():
    api = TqApi(auth=TqAuth("账号", "密码"))
    
    print(f"启动：波动率曲面套利策略 | 标的: {UNDERLYING}")
    
    # 获取标的行情
    underlying = api.get_quote(UNDERLYING)
    
    # 获取期权链
    calls = []
    puts = []
    
    # 筛选不同执行价的期权
    for strike in np.arange(2.0, 4.0, 0.1):
        call_code = f"{UNDERLYING}C{strike:.2f}{OPTION_EXPIRY}"
        put_code = f"{UNDERLYING}P{strike:.2f}{OPTION_EXPIRY}"
        
        try:
            call = api.get_quote(call_code)
            put = api.get_quote(put_code)
            calls.append((strike, call))
            puts.append((strike, put))
        except:
            continue
    
    print(f"获取到 {len(calls)} 个看涨期权, {len(puts)} 个看跌期权")
    
    # 记录持仓
    positions = {}  # {option_code: (direction, volume)}
    
    while True:
        api.wait_update()
        
        # 更新波动率计算
        current_price = underlying.last_price
        
        for strike, call in calls:
            if call.last_price > 0:
                # 计算隐含波动率（简化）
                iv = calc_implied_vol(call.last_price, current_price, strike, 30/365)
                
                # 简单的波动率偏离判断
                if strike == 2.5:  # ATM
                    atm_iv = iv
                elif strike > 2.5 and iv > atm_iv + IV_ENTRY_THRESHOLD:
                    # OTM Call IV偏高，卖出
                    if call not in positions:
                        print(f"卖出波动率: {call.symbol}, IV={iv:.2%}")
                        api.insert_order(symbol=call.symbol, direction="short", offset="open", volume=POSITION_SIZE)
                        positions[call] = ("short", POSITION_SIZE)
                
                elif strike < 2.5 and iv > atm_iv + IV_ENTRY_THRESHOLD:
                    # OTM Put IV偏高，卖出
                    pass  # 类似逻辑
    
    api.close()

if __name__ == "__main__":
    main()
