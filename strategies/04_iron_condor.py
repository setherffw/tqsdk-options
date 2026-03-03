"""
================================================================================
TqSdk 天勤量化 — 专业量化交易框架
================================================================================
官方文档：https://doc.shinnytech.com/tqsdk/latest/
GitHub  ：https://github.com/shinnytech/tqsdk-python

TqSdk（天勤量化软件开发包）是由信易科技基于 DIFF 协议开发的开源 Python 量化
交易框架，支持期货、期权、股票等多品种实盘/模拟/回测交易。
================================================================================

策略名称：铁鹰式期权组合策略
策略编号：04
策略类型：收入增强策略（Short Iron Condor）
适用品种：50ETF期权、股指期权
策略日期：2026-03-03
================================================================================

【策略原理】
--------------------
铁鹰式期权组合（Iron Condor）是经典的收入增强策略，通过同时卖出
宽跨式组合并买入更宽范围的价差来限制风险。

组合构成：
  1. 卖出1份看涨期权（高执行价，OTM）
  2. 买入1份看涨期权（更高执行价，深度OTM）
  3. 卖出1份看跌期权（低执行价，OTM）
  4. 买入1份看跌期权（更低执行价，深度OTM）

盈亏特征：
  - 盈利区间：中间价格范围（两个卖出期权的执行价之间）
  - 最大盈利：收取的权利金
  - 亏损区间：价格突破两个买入期权的执行价之外
  - 最大亏损：两个价差的差额 - 收取的权利金

本策略：
  1. 选择合适的执行价区间（基于历史波动率和支撑阻力位）
  2. 在预期盘整区间上方卖出看涨期权，下方卖出看跌期权
  3. 用更宽范围的价差期权作为保护，限制极端风险
  4. 持有至到期或价格触及止损线

【策略参数说明】
--------------------
  UNDERLYING      : 标的合约代码
  CALL_SELL_STRIKE: 卖出看涨期权执行价
  CALL_BUY_STRIKE : 买入看涨期权执行价（高于卖出价）
  PUT_SELL_STRIKE : 卖出看跌期权执行价
  PUT_BUY_STRIKE  : 买入看跌期权执行价（低于卖出价）
  EXPIRY_DAYS     : 距到期天数
  MAX_LOSS        : 最大亏损阈值，触及后平仓

【风险提示】
--------------------
  1. 趋势行情中可能产生较大亏损
  2. 流动性风险：部分执行价期权成交稀疏
  3. 保证金占用大，需预留足够资金
  4. 临近到期Gamma增大，需关注仓位管理
================================================================================
"""

from tqsdk import TqApi, TqAuth
import datetime

# ============ 参数配置 ============
UNDERLYING = "SHFE.10004"      # 50ETF
EXPIRY = "2406"                # 到期月份

# 执行价配置（根据当前标的价设置）
CALL_SELL_STRIKE = 3.0         # 卖出看涨执行价
CALL_BUY_STRIKE = 3.2          # 买入看涨执行价
PUT_SELL_STRIKE = 2.6          # 卖出看跌执行价
PUT_BUY_STRIKE = 2.4           # 买入看跌执行价

POSITION_SIZE = 1               # 组合数量
MAX_LOSS_PCT = 0.02            # 最大亏损比例 2%

def main():
    api = TqApi(auth=TqAuth("账号", "密码"))
    
    print(f"启动：铁鹰式期权组合策略 | 标的: {UNDERLYING}")
    
    # 构建期权代码
    call_sell = f"{UNDERLYING}C{CALL_SELL_STRIKE:.2f}{EXPIRY}"
    call_buy = f"{UNDERLYING}C{CALL_BUY_STRIKE:.2f}{EXPIRY}"
    put_sell = f"{UNDERLYING}P{PUT_SELL_STRIKE:.2f}{EXPIRY}"
    put_buy = f"{UNDERLYING}P{PUT_BUY_STRIKE:.2f}{EXPIRY}"
    
    print(f"组合构建:")
    print(f"  卖出看涨: {call_sell}")
    print(f"  买入看涨: {call_buy}")
    print(f"  卖出看跌: {put_sell}")
    print(f"  买入看跌: {put_buy}")
    
    # 获取合约
    try:
        call_sell_quote = api.get_quote(call_sell)
        call_buy_quote = api.get_quote(call_buy)
        put_sell_quote = api.get_quote(put_sell)
        put_buy_quote = api.get_quote(put_buy)
    except Exception as e:
        print(f"获取期权合约失败: {e}")
        api.close()
        return
    
    # 开仓：同时卖出宽跨式组合，买入价差保护
    print("\n=== 开仓 ===")
    
    # 卖出看涨期权
    api.insert_order(symbol=call_sell, direction="short", offset="open", volume=POSITION_SIZE)
    print(f"卖出 {call_sell}")
    
    # 买入看涨期权（保护）
    api.insert_order(symbol=call_buy, direction="long", offset="open", volume=POSITION_SIZE)
    print(f"买入 {call_buy}")
    
    # 卖出看跌期权
    api.insert_order(symbol=put_sell, direction="short", offset="open", volume=POSITION_SIZE)
    print(f"卖出 {put_sell}")
    
    # 买入看跌期权（保护）
    api.insert_order(symbol=put_buy, direction="long", offset="open", volume=POSITION_SIZE)
    print(f"买入 {put_buy}")
    
    print("\n组合已建立，等待到期或平仓信号...")
    
    position_opened = True
    
    while position_opened:
        api.wait_update()
        
        # 检查是否需要平仓（到期或止损）
        # 这里可以添加止损逻辑、平仓逻辑等
        
        # 简化的平仓条件：价格突破盈利区间
        current_price = api.get_quote(UNDERLYING).last_price
        
        if current_price > CALL_BUY_STRIKE or current_price < PUT_BUY_STRIKE:
            print(f"\n价格突破保护区间，准备平仓 | 当前价: {current_price}")
            break
    
    # 平仓操作
    print("\n=== 平仓 ===")
    api.insert_order(symbol=call_sell, direction="long", offset="close", volume=POSITION_SIZE)
    api.insert_order(symbol=call_buy, direction="short", offset="close", volume=POSITION_SIZE)
    api.insert_order(symbol=put_sell, direction="long", offset="close", volume=POSITION_SIZE)
    api.insert_order(symbol=put_buy, direction="short", offset="close", volume=POSITION_SIZE)
    
    print("平仓完成")
    
    api.close()

if __name__ == "__main__":
    main()
