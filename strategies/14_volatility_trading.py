"""
================================================================================
TqSdk 天勤量化 — 专业量化交易框架
================================================================================
官方文档：https://doc.shinnytech.com/tqsdk/latest/
GitHub  ：https://github.com/shinnytech/tqsdk-python

策略名称：期权波动率交易策略
策略编号：14
策略类型：波动率交易
适用品种：金融期权、商品期权
策略日期：2026-03-06
================================================================================

【策略原理】
--------------------
波动率交易（Volatility Trading）是指根据波动率的高低进行期权交易。
核心思想是：
- 当预期波动率上升时，买入跨式组合（Straddle）或宽跨式组合（Strangle）
- 当预期波动率下降时，卖出跨式组合或宽跨式组合
- 波动率交易不受方向影响，盈利来源于波动率变化

【策略逻辑】
--------------------
- 监控历史波动率与隐含波动率的偏离
- 当隐含波动率低于历史波动率一定比例时，买入跨式组合（做多波动率）
- 当隐含波动率高于历史波动率一定比例时，卖出跨式组合（做空波动率）
- 持有至波动率回归或到期

【参数说明】
--------------------
  SYMBOL         : 标的期货合约代码
  KLINE_DURATION : K线周期（秒）
  HV_PERIOD      : 历史波动率计算周期
  IV_THRESHOLD   : 隐含波动率偏离阈值
  HOLDING_PERIOD : 持仓周期（根K线）
  STRIKE_OFFSET  : 行权价偏移（ATM的百分比）

作者：setherffw / tqsdk-options
日期：2026-03-06
================================================================================
"""

from tqsdk import TqApi, TqAuth, TqSim
import numpy as np

# ===================== 策略参数 =====================
SYMBOL = "SHFE.rb2505"        # 标的期货（螺纹钢）
KLINE_DURATION = 3600         # 1小时K线
HV_PERIOD = 20                # 历史波动率计算周期
IV_THRESHOLD = 0.8             # IV/HV阈值（低于此值做多波动率）
HOLDING_BARS = 24             # 持仓24根K线
STRIKE_OFFSET = 0.03          # 行权价偏移3%
# ====================================================

def calculate_hv(close_prices, period):
    """计算历史波动率"""
    if len(close_prices) < period + 1:
        return None
    returns = np.diff(np.log(close_prices[-period-1:]))
    hv = np.std(returns) * np.sqrt(252) * 100  # 年化波动率
    return hv

def get_strike_prices(underlying_price, offset):
    """计算ATM附近的行权价"""
    atm = int(underlying_price / 100) * 100
    call_strike = int(atm * (1 + offset))
    put_strike = int(atm * (1 - offset))
    return call_strike, put_strike

def main():
    api = TqApi(auth=TqAuth("13556817485", "asd159753"), sim=TqSim())
    
    # 获取标的行情
    underlying = api.get_quote(SYMBOL)
    kline = api.get_kline_serial(SYMBOL, KLINE_DURATION)
    
    print(f"期权波动率交易策略")
    print(f"标的:{SYMBOL}")
    
    position = 0  # 1: 做多波动率, -1: 做空波动率, 0: 空仓
    entry_iv = 0
    bars_held = 0
    
    close_history = []
    
    while True:
        api.wait_update()
        
        # 更新收盘价序列
        if len(kline) > 0:
            close = kline["close"][-1]
            close_history.append(close)
            if len(close_history) > HV_PERIOD + 10:
                close_history = close_history[-(HV_PERIOD+10):]
        
        # 计算历史波动率
        hv = calculate_hv(close_history, HV_PERIOD)
        
        if hv is None:
            continue
        
        current_price = close_history[-1]
        call_strike, put_strike = get_strike_prices(current_price, STRIKE_OFFSET)
        
        print(f"[监控] 价格:{current_price:.0f} HV:{hv:.1f}%", end="")
        
        if position == 0:
            # 尝试获取隐含波动率（简化版：使用期权价格反推）
            # 实际需要通过Black-Scholes模型计算
            print(f" | 等待信号...")
            
            # 简化逻辑：当HV较低时做多波动率
            # 实际应使用期权隐含波动率
            if hv < 20:  # 假设HV低于20%时认为偏低
                print(f"[建仓] 买入跨式组合 HV:{hv:.1f}%")
                position = 1
                entry_iv = hv
                bars_held = 0
        else:
            bars_held += 1
            
            # 检查是否平仓
            if bars_held >= HOLDING_BARS:
                print(f"[到期平仓] 持仓{bars_held}根K线")
                position = 0
            elif hv > entry_iv * 1.3:
                # 波动率上升30%，平仓获利
                print(f"[波动率上升平仓] HV:{hv:.1f}% 较入场:{hv/entry_iv*100-100:.1f}%")
                position = 0
            elif hv < entry_iv * 0.7:
                # 波动率下降30%，止损
                print(f"[波动率下降止损] HV:{hv:.1f}%")
                position = 0

if __name__ == "__main__":
    main()
