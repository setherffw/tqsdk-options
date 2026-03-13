"""
策略名称：50ETF/300ETF跨标的期权对冲组合策略
策略类型：跨标的期权 + 波动率价差对冲
标的：50ETF期权 + 300ETF期权
描述：
    50ETF（沪深蓝筹）与300ETF（沪深300）高度相关但存在阶段性波动率价差。
    策略逻辑：
      1. 计算两者的相对隐含波动率偏差（RV_spread = IV_50 - IV_300）
      2. 当RV_spread高于历史均值+1.5σ时：
         - 卖出50ETF近月ATM跨式（IV偏高）
         - 买入300ETF近月ATM跨式（IV相对低，对冲方向性风险）
      3. 当RV_spread低于均值-1.5σ时：反向操作
      4. RV_spread均值回归到±0.5σ内时平仓
    目的：通过跨标的IV价差交易，降低单一标的Vega暴露，
    获取两者IV均值回归收益，同时用对冲腿压缩最大回撤。
"""

from tqsdk import TqApi, TqAuth, TqSim
import numpy as np

# ===== 参数 =====
SYMBOL_50  = "SSE.510050"     # 50ETF现货
SYMBOL_300 = "SSE.510300"     # 300ETF现货

# 期权合约（示例，需替换为当前有效合约）
OPT_50_CALL  = "SSE.10004173"  # 50ETF近月ATM认购
OPT_50_PUT   = "SSE.10004175"  # 50ETF近月ATM认沽
OPT_300_CALL = "SSE.10004273"  # 300ETF近月ATM认购
OPT_300_PUT  = "SSE.10004275"  # 300ETF近月ATM认沽

LOOKBACK     = 30    # RV_spread统计窗口（日）
ENTRY_STD    = 1.5   # 开仓阈值
EXIT_STD     = 0.5   # 平仓阈值
VOLUME       = 1     # 手数

api = TqApi(TqSim(), auth=TqAuth("YOUR_ACCOUNT", "YOUR_PASSWORD"))

kl_50  = api.get_kline_serial(SYMBOL_50,  86400, data_length=LOOKBACK + 25)
kl_300 = api.get_kline_serial(SYMBOL_300, 86400, data_length=LOOKBACK + 25)

def calc_hv20(kl):
    """20日已实现波动率"""
    closes = kl["close"].values
    r = np.diff(np.log(closes[-21:]))
    return float(np.std(r) * np.sqrt(252))

def calc_rv_spread_series(kl_50, kl_300, window=LOOKBACK):
    """历史RV_spread序列"""
    spreads = []
    for i in range(window):
        idx = -(window - i + 21)
        r50  = np.diff(np.log(kl_50["close"].values[idx:idx+21]))
        r300 = np.diff(np.log(kl_300["close"].values[idx:idx+21]))
        hv50  = float(np.std(r50)  * np.sqrt(252))
        hv300 = float(np.std(r300) * np.sqrt(252))
        spreads.append(hv50 - hv300)
    return np.array(spreads)

current_side = 0   # 1=卖50买300 -1=买50卖300

try:
    while True:
        api.wait_update()

        if not (api.is_changing(kl_50.iloc[-1], "datetime") or
                api.is_changing(kl_300.iloc[-1], "datetime")):
            continue

        # ---- 计算当前RV价差 ----
        hv50  = calc_hv20(kl_50)
        hv300 = calc_hv20(kl_300)
        rv_spread = hv50 - hv300

        # 历史统计
        hist_spreads = calc_rv_spread_series(kl_50, kl_300)
        mu    = float(np.mean(hist_spreads))
        sigma = float(np.std(hist_spreads))
        zscore = (rv_spread - mu) / (sigma + 1e-8)

        print(f"[跨标的期权] HV50={hv50:.2%}  HV300={hv300:.2%}  "
              f"RV_spread={rv_spread:.3f}  Z={zscore:.2f}  仓位={current_side}")

        # ---- 平仓 ----
        if current_side == 1 and zscore < EXIT_STD:
            # 买回50跨式，卖出300跨式
            api.insert_order(OPT_50_CALL,  direction="BUY",  offset="CLOSE", volume=VOLUME)
            api.insert_order(OPT_50_PUT,   direction="BUY",  offset="CLOSE", volume=VOLUME)
            api.insert_order(OPT_300_CALL, direction="SELL", offset="CLOSE", volume=VOLUME)
            api.insert_order(OPT_300_PUT,  direction="SELL", offset="CLOSE", volume=VOLUME)
            current_side = 0
            print("  → 平仓（卖50/买300跨式）")
        elif current_side == -1 and zscore > -EXIT_STD:
            api.insert_order(OPT_50_CALL,  direction="SELL", offset="CLOSE", volume=VOLUME)
            api.insert_order(OPT_50_PUT,   direction="SELL", offset="CLOSE", volume=VOLUME)
            api.insert_order(OPT_300_CALL, direction="BUY",  offset="CLOSE", volume=VOLUME)
            api.insert_order(OPT_300_PUT,  direction="BUY",  offset="CLOSE", volume=VOLUME)
            current_side = 0
            print("  → 平仓（买50/卖300跨式）")

        # ---- 开仓 ----
        if current_side == 0:
            if zscore > ENTRY_STD:
                # 50IV相对偏高 → 卖出50跨式 + 买入300跨式对冲
                api.insert_order(OPT_50_CALL,  direction="SELL", offset="OPEN", volume=VOLUME)
                api.insert_order(OPT_50_PUT,   direction="SELL", offset="OPEN", volume=VOLUME)
                api.insert_order(OPT_300_CALL, direction="BUY",  offset="OPEN", volume=VOLUME)
                api.insert_order(OPT_300_PUT,  direction="BUY",  offset="OPEN", volume=VOLUME)
                current_side = 1
                print(f"  → 开仓：卖50跨式+买300跨式  Z={zscore:.2f}")
            elif zscore < -ENTRY_STD:
                # 300IV相对偏高 → 买入50跨式 + 卖出300跨式
                api.insert_order(OPT_50_CALL,  direction="BUY",  offset="OPEN", volume=VOLUME)
                api.insert_order(OPT_50_PUT,   direction="BUY",  offset="OPEN", volume=VOLUME)
                api.insert_order(OPT_300_CALL, direction="SELL", offset="OPEN", volume=VOLUME)
                api.insert_order(OPT_300_PUT,  direction="SELL", offset="OPEN", volume=VOLUME)
                current_side = -1
                print(f"  → 开仓：买50跨式+卖300跨式  Z={zscore:.2f}")

finally:
    api.close()
