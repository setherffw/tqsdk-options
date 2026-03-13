"""
策略名称：多因子期权波动率截面选择策略
策略类型：多因子截面 + 波动率相对价值
标的：50ETF期权（SHFE.510050）
描述：
    同时考虑多个因子对期权进行截面打分：
      F1 - 隐含波动率相对历史分位（IV Rank）
      F2 - Put/Call比率（PCR，情绪因子）
      F3 - 近月远月IV价差（期限结构因子）
    综合得分高时认为IV被高估，卖出跨式组合（sell straddle）；
    综合得分低时认为IV被低估，买入跨式组合（buy straddle）。
    每日收盘前重新评分，当得分穿越阈值时换仓。
"""

from tqsdk import TqApi, TqAuth, TqSim
from tqsdk.tafunc import time_to_datetime
import numpy as np
import datetime

# ===== 参数 =====
UNDERLYING = "SSE.510050"     # 50ETF
NEAR_MONTH = "SSE.10004173"   # 近月ATM合约示例（需替换为当前有效合约）
FAR_MONTH  = "SSE.10004174"   # 远月ATM合约示例
STRIKE     = 3.0              # ATM行权价（近似）
LOOKBACK_IV = 60              # IV历史分位回看（日）
ENTRY_SCORE = 1.5             # 开仓得分阈值
EXIT_SCORE  = 0.5             # 平仓得分阈值
VOLUME      = 1               # 手数

api = TqApi(TqSim(), auth=TqAuth("YOUR_ACCOUNT", "YOUR_PASSWORD"))

# 获取K线用于估算历史波动率
kl_underlying = api.get_kline_serial(UNDERLYING, 86400, data_length=LOOKBACK_IV + 5)

# 模拟IV序列（实盘中应通过tqsdk期权接口获取）
def get_current_iv():
    """从期权报价计算隐含波动率（此处用已实现波动率近似）"""
    closes = kl_underlying["close"].values
    returns = np.diff(np.log(closes[-21:]))
    hv20 = float(np.std(returns) * np.sqrt(252))
    return hv20

def get_iv_rank(current_iv):
    """计算IV Rank：当前IV在过去N日的百分位"""
    closes = kl_underlying["close"].values
    # 滚动20日HV序列
    hv_series = []
    for i in range(LOOKBACK_IV):
        idx = -(LOOKBACK_IV - i + 21)
        r = np.diff(np.log(closes[idx:idx+21]))
        hv_series.append(float(np.std(r) * np.sqrt(252)))
    lo, hi = min(hv_series), max(hv_series)
    if hi == lo:
        return 0.5
    return (current_iv - lo) / (hi - lo)

def get_pcr():
    """Put/Call成交量比（模拟，实盘从交易所数据获取）"""
    # 简化：根据最近标的价格与20日均线偏离度代替PCR
    closes = kl_underlying["close"].values
    ma20 = np.mean(closes[-20:])
    deviation = (closes[-1] - ma20) / ma20
    # 下跌时PCR偏高
    return 1.0 - deviation * 10

def get_term_structure():
    """近远月IV差（正数代表正向结构，期权正常升水）"""
    # 简化：用近月/远月隐含波动率差（此处用滚动10日/30日HV代替）
    closes = kl_underlying["close"].values
    r10 = np.diff(np.log(closes[-11:]))
    r30 = np.diff(np.log(closes[-31:]))
    hv10 = float(np.std(r10) * np.sqrt(252))
    hv30 = float(np.std(r30) * np.sqrt(252))
    return hv10 - hv30   # >0 近月IV > 远月 → 反向结构 → IV高估

current_side = 0  # 1=卖出跨式 -1=买入跨式

try:
    while True:
        api.wait_update()

        if not api.is_changing(kl_underlying.iloc[-1], "datetime"):
            continue

        # ---- 多因子截面打分 ----
        iv     = get_current_iv()
        iv_rnk = get_iv_rank(iv)       # [0,1]，越高IV越贵
        pcr    = get_pcr()              # >1 情绪偏空，IV偏高
        term   = get_term_structure()   # >0 近高远低，反向结构，IV偏高

        # 标准化到[-1, 1]的打分
        f1 = (iv_rnk - 0.5) * 2        # IV rank分
        f2 = np.tanh(pcr - 1.0)        # PCR分
        f3 = np.tanh(term * 20)        # 期限结构分

        score = (f1 + f2 + f3) / 3     # 综合得分，>0 IV偏高

        print(f"[多因子期权] IV={iv:.2%}  IVRank={iv_rnk:.2f}  PCR={pcr:.2f}  Term={term:.3f}  Score={score:.3f}")

        # ---- 平仓 ----
        if current_side == 1 and score < EXIT_SCORE:
            # 平卖出跨式
            api.insert_order(NEAR_MONTH, direction="BUY",  offset="CLOSE", volume=VOLUME)
            current_side = 0
            print("  → 平卖出跨式")
        elif current_side == -1 and score > -EXIT_SCORE:
            api.insert_order(NEAR_MONTH, direction="SELL", offset="CLOSE", volume=VOLUME)
            current_side = 0
            print("  → 平买入跨式")

        # ---- 开仓 ----
        if current_side == 0:
            if score > ENTRY_SCORE:
                # IV高估 → 卖出跨式（卖认购+卖认沽）
                api.insert_order(NEAR_MONTH, direction="SELL", offset="OPEN",
                                 volume=VOLUME, limit_price=-1)
                current_side = 1
                print(f"  → 开卖出跨式  Score={score:.3f}")
            elif score < -ENTRY_SCORE:
                # IV低估 → 买入跨式
                api.insert_order(NEAR_MONTH, direction="BUY", offset="OPEN",
                                 volume=VOLUME)
                current_side = -1
                print(f"  → 开买入跨式  Score={score:.3f}")

finally:
    api.close()
