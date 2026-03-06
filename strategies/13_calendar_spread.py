"""
================================================================================
TqSdk 天勤量化 — 专业量化交易框架
================================================================================
官方文档：https://doc.shinnytech.com/tqsdk/latest/
GitHub  ：https://github.com/shinnytech/tqsdk-python

策略名称：期权日历价差策略
策略编号：13
策略类型：期权价差套利
适用品种：金融期权、商品期权
策略日期：2026-03-06
================================================================================

【策略原理】
--------------------
日历价差（Calendar Spread）是指卖出近月期权同时买入相同行权价的远月期权。
主要收益来源：
1. 时间价值衰减：近月期权时间价值衰减速度快于远月期权
2. 波动率变化：近月合约对波动率更敏感
3. 风险有限：最大亏损限于净权利金支出

【策略逻辑】
--------------------
- 卖出近月平值期权（Call/Put）
- 买入远月相同行权价期权
- 持有至近月到期或价差达到目标收益平仓

【参数说明】
--------------------
  SYMBOL         : 标的期货合约代码
  STRIKE         : 行权价
  OPTION_TYPE    : 期权类型 ("CALL" 或 "PUT")
  NEAR_MONTH     : 近月合约到期月份
  FAR_MONTH      : 远月合约到期月份
  KLINE_DURATION : K线周期（秒）
  EXIT_THRESHOLD : 平仓收益率阈值

作者：setherffw / tqsdk-options
日期：2026-03-06
================================================================================
"""

from tqsdk import TqApi, TqAuth, TqSim
from tqsdk.tafunc import time_to_str
import datetime

# ===================== 策略参数 =====================
SYMBOL = "SHFE.cu2505"        # 标的期货（沪铜）
STRIKE = 76000                # 行权价
OPTION_TYPE = "CALL"          # 期权类型：CALL 或 PUT
NEAR_MONTH = "2505"           # 近月
FAR_MONTH = "2509"            # 远月
KLINE_DURATION = 3600         # 1小时K线
EXIT_THRESHOLD = 0.3          # 30%收益率平仓
LOT_SIZE = 1                  # 手数
# ====================================================

def get_option_code(symbol, month, strike, opt_type):
    """生成期权合约代码"""
    # 上期所期权代码格式：期权品类+标的合约+类型+行权价
    if "cu" in symbol.lower():
        prefix = "CU"
    elif "au" in symbol.lower():
        prefix = "AU"
    elif "ag" in symbol.lower():
        prefix = "AG"
    else:
        prefix = "IO"
    
    opt_type_code = "C" if opt_type == "CALL" else "P"
    return f"SHFE.{prefix}{month}{opt_type_code}{strike // 1000}"

def calc_calendar_spread_premium(near_premium, far_premium):
    """计算日历价差价值"""
    return far_premium - near_premium

def main():
    api = TqApi(auth=TqAuth("13556817485", "asd159753"), sim=TqSim())
    
    # 生成期权合约代码
    near_option = get_option_code(SYMBOL, NEAR_MONTH, STRIKE, OPTION_TYPE)
    far_option = get_option_code(SYMBOL, FAR_MONTH, STRIKE, OPTION_TYPE)
    
    print(f"期权日历价差策略")
    print(f"标的:{SYMBOL} 行权价:{STRIKE}")
    print(f"近月期权:{near_option}")
    print(f"远月期权:{far_option}")
    
    # 持仓状态
    position = 0  # 1: 持有价差, 0: 空仓
    entry_spread = 0
    
    while True:
        api.wait_update()
        
        try:
            near_quote = api.get_quote(near_option)
            far_quote = api.get_quote(far_option)
            
            near_premium = near_quote.get("last_price", 0)
            far_premium = far_quote.get("last_price", 0)
            
            if near_premium == 0 or far_premium == 0:
                continue
            
            current_spread = calc_calendar_spread_premium(near_premium, far_premium)
            
            if position == 0:
                # 建仓：卖出近月期权，买入远月期权
                print(f"[建仓] 近月权利金:{near_premium} 远月权利金:{far_premium} 价差:{current_spread}")
                entry_spread = current_spread
                position = 1
            else:
                # 计算收益率
                pnl_ratio = (current_spread - entry_spread) / abs(entry_spread) if entry_spread != 0 else 0
                
                if pnl_ratio > EXIT_THRESHOLD:
                    print(f"[平仓] 当前价差:{current_spread} 收益率:{pnl_ratio*100:.1f}%")
                    position = 0
                elif pnl_ratio < -EXIT_THRESHOLD:
                    print(f"[止损] 当前价差:{current_spread} 收益率:{pnl_ratio*100:.1f}%")
                    position = 0
                    
        except Exception as e:
            print(f"获取行情失败: {e}")
            continue

if __name__ == "__main__":
    main()
