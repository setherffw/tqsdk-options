"""
================================================================================
TqSdk 天勤量化 — 专业量化交易框架
================================================================================
官方文档：https://doc.shinnytech.com/tqsdk/latest/
GitHub  ：https://github.com/shinnytech/tqsdk-python

TqSdk（天勤量化软件开发包）是由信易科技基于 DIFF 协议开发的开源 Python 量化
交易框架，支持期货、期权、股票等多品种实盘/模拟/回测交易。其核心特性包括：
  · 全品种覆盖：沪深两市期权、商品期货期权、金融期货期权
  · 实时行情推送：基于 WebSocket 的 Tick 级别行情
  · 风险管理：内置持仓、保证金、盈亏实时监控
  · 回测引擎：支持日线/分钟线/Tick 多精度历史回测
  · 简洁 API：async/await 协程模型，代码清晰易维护
================================================================================

策略名称：50ETF 期权 Delta 动态对冲策略
策略编号：01
策略类型：Delta 中性对冲
适用品种：上交所 50ETF 期权（SHFE.10004XXX）
策略日期：2026-03-02
================================================================================

【策略原理】
--------------------
Delta 对冲（Delta Hedging）是期权交易中最基础、最经典的风险管理方法。
其核心思想是通过持有数量适当的标的资产（或期货）来抵消期权头寸的 Delta 风险，
使整体组合保持 Delta 中性（Delta ≈ 0）。

Delta（Δ）是期权价格关于标的资产价格的一阶偏导数，表示标的资产价格变动 1 单位
时，期权理论价格的变动量：
  · 看涨期权（Call）：0 < Δ < 1
  · 看跌期权（Put）：-1 < Δ < 0

动态对冲要求：
  1. 初始建仓时，根据所持期权的 Delta 值，买入或卖出对应数量的标的资产（50ETF
     现货或其期货替代）以使组合 Delta 接近零。
  2. 随着标的价格波动和时间流逝，Delta 会不断变化，需要定期或按阈值重新调整对
     冲头寸，即"再平衡"（Rebalancing）。
  3. 每次再平衡会带来交易成本（手续费、滑点），因此需要在对冲精度和成本之间取
     得平衡。

【策略参数说明】
--------------------
  OPTION_CODE    : 目标期权合约代码（近月平值 Call，需手动选取或由选股模块自动
                   确定）
  HEDGE_SYMBOL   : 对冲工具合约代码（50ETF 期货或现货替代）
  OPTION_LOTS    : 期权持仓数量（卖出 Call 张数，每张对应 10000 份 ETF）
  DELTA_THRESHOLD: 组合 Delta 偏离阈值，超过此值触发再平衡
  LOT_SIZE       : 每张期权对应标的手数换算系数
  MAX_HEDGE_LOTS : 对冲仓位上限（风控参数）

【风险提示】
--------------------
  1. 本策略仅用于教学演示，不构成任何投资建议。
  2. 期权隐含波动率突变（Vega 风险）、流动性风险等均可能导致策略失效。
  3. Gamma 较大时（临近到期或深度实值/虚值），Delta 变化加速，对冲频率需相应
     提高，否则对冲误差会显著增大。
  4. 实盘使用前务必在仿真账户（TqSim）中充分测试，并结合自身风险承受能力设置
     止损线。

【主要流程】
--------------------
  Step 1  连接 TqSdk，订阅期权合约和对冲标的行情
  Step 2  查询期权 Greeks（Delta）—— 通过 TqSdk get_option_greeks 接口
  Step 3  计算当前组合 Delta = 期权持仓 Delta × 合约乘数
  Step 4  若 |组合 Delta| > DELTA_THRESHOLD，发出对冲指令
  Step 5  等待成交，记录对冲日志
  Step 6  循环监控（每 Tick 更新）

================================================================================
"""

import asyncio
import datetime
import logging
from typing import Optional

from tqsdk import TqApi, TqAuth, TqSim, TqAccount
from tqsdk.objs import Quote, Order, Position

# ─── 日志配置 ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"delta_hedge_{datetime.date.today()}.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("DeltaHedge")

# ─── 策略参数 ────────────────────────────────────────────────────────────────
# 期权合约：上交所 50ETF 近月平值看涨期权（示例代码，需按实际月份修改）
OPTION_CODE: str = "SHFE.10004438"          # 50ETF 期权合约代码（示例）
HEDGE_SYMBOL: str = "SSE.510050"            # 50ETF 现货（作为对冲标的示意）
OPTION_LOTS: int = 10                        # 卖出 Call 期权手数（张）
OPTION_CONTRACT_MULTIPLIER: int = 10000     # 每张期权对应 10000 份 ETF
DELTA_THRESHOLD: float = 0.05               # Delta 偏离触发阈值
MAX_HEDGE_LOTS: int = 50                    # 对冲头寸上限（手）
RECHECK_INTERVAL_SEC: int = 30             # 强制再检查间隔（秒）

# ─── 辅助函数 ────────────────────────────────────────────────────────────────

def calc_portfolio_delta(option_delta: float, option_lots: int, option_direction: str) -> float:
    """
    计算期权头寸的组合 Delta。

    Args:
        option_delta    : 单张期权的 Delta 值（Black-Scholes 理论值）
        option_lots     : 持仓手数
        option_direction: "sell" 表示卖出方向，"buy" 表示买入方向

    Returns:
        float: 组合 Delta（以标的 ETF 份数衡量）
    """
    sign = -1 if option_direction == "sell" else 1
    return sign * option_delta * option_lots * OPTION_CONTRACT_MULTIPLIER


def calc_hedge_lots(portfolio_delta: float, etf_price: float) -> int:
    """
    根据组合 Delta 计算需要买卖的 ETF 手数（对冲量）。
    
    由于 50ETF 现货最小交易单位为 100 份，这里取整到最近的 100 倍。

    Args:
        portfolio_delta: 当前组合 Delta（ETF 份数）
        etf_price      : ETF 当前价格（元）

    Returns:
        int: 需要买入（正）或卖出（负）的 ETF 手数
    """
    # 对冲量：为使 Delta 归零，需要买入 -portfolio_delta 份 ETF
    lots = -portfolio_delta / 100  # 每手 100 份
    return int(round(lots))


# ─── 主策略逻辑 ──────────────────────────────────────────────────────────────

async def run_delta_hedge():
    """
    Delta 动态对冲策略主协程。

    使用 TqSdk 的异步 API，实时监控期权 Greeks 并在 Delta 超过阈值时
    自动执行对冲交易。
    """
    # ── 初始化 TqSdk（仿真账户，实盘替换 TqSim 为 TqAccount） ──
    api = TqApi(
        account=TqSim(init_balance=500000),   # 50 万仿真资金
        auth=TqAuth("YOUR_TIANQIN_USERNAME", "YOUR_TIANQIN_PASSWORD"),
    )

    logger.info("="*60)
    logger.info("Delta 动态对冲策略启动")
    logger.info(f"期权合约  : {OPTION_CODE}")
    logger.info(f"对冲标的  : {HEDGE_SYMBOL}")
    logger.info(f"期权持仓  : 卖出 {OPTION_LOTS} 张")
    logger.info(f"Delta阈值 : {DELTA_THRESHOLD}")
    logger.info("="*60)

    try:
        # ── 订阅行情 ──────────────────────────────────────────────
        quote_option: Quote = api.get_quote(OPTION_CODE)
        quote_hedge: Quote  = api.get_quote(HEDGE_SYMBOL)

        # ── 查询账户持仓 ──────────────────────────────────────────
        position_option: Position = api.get_position(OPTION_CODE)
        position_hedge: Position  = api.get_position(HEDGE_SYMBOL)

        logger.info("行情订阅成功，开始监控...")

        last_recheck = datetime.datetime.now()
        pending_order: Optional[Order] = None

        while True:
            await api.wait_update()

            now = datetime.datetime.now()
            time_elapsed = (now - last_recheck).seconds

            # ── 检查行情是否有效 ──────────────────────────────────
            if quote_option.last_price != quote_option.last_price:  # NaN 检查
                logger.warning("期权行情暂无有效价格，跳过本次更新")
                continue

            # ── 获取期权 Greeks（Delta）──────────────────────────
            # TqSdk 通过 quote 对象的 Greeks 字段提供实时 Greeks 计算
            option_delta = getattr(quote_option, "delta", None)
            if option_delta is None:
                logger.warning("Delta 数据暂不可用，等待下一个 Tick...")
                continue

            etf_price = quote_hedge.last_price
            if not etf_price or etf_price != etf_price:
                logger.warning("ETF 价格暂不可用，跳过")
                continue

            # ── 计算组合 Delta ────────────────────────────────────
            port_delta = calc_portfolio_delta(
                option_delta=option_delta,
                option_lots=OPTION_LOTS,
                option_direction="sell",  # 卖出期权
            )

            # 加上现有对冲头寸的 Delta（现货多头 Delta = 持仓份数）
            hedge_holding = position_hedge.pos_long_his + position_hedge.pos_long_today
            net_delta = port_delta + hedge_holding * 100  # 每手 100 份

            logger.debug(
                f"期权Delta={option_delta:.4f} | 组合Delta={port_delta:.0f} | "
                f"对冲持仓={hedge_holding}手 | 净Delta={net_delta:.0f}"
            )

            # ── 判断是否需要再平衡 ────────────────────────────────
            delta_in_lots = abs(net_delta) / 100  # 转换为手数
            need_rebalance = (
                delta_in_lots > DELTA_THRESHOLD * OPTION_LOTS * OPTION_CONTRACT_MULTIPLIER / 100
                or time_elapsed >= RECHECK_INTERVAL_SEC
            )

            if not need_rebalance:
                continue

            last_recheck = now

            # ── 计算对冲交易量 ────────────────────────────────────
            target_hedge_lots = calc_hedge_lots(port_delta, etf_price)
            delta_lots_needed = target_hedge_lots - hedge_holding

            if delta_lots_needed == 0:
                logger.info(f"[对冲] 净Delta={net_delta:.0f}，无需调整")
                continue

            # ── 风控检查 ──────────────────────────────────────────
            new_hedge = hedge_holding + delta_lots_needed
            if abs(new_hedge) > MAX_HEDGE_LOTS:
                logger.warning(
                    f"[风控] 目标对冲手数 {new_hedge} 超过上限 {MAX_HEDGE_LOTS}，已截断"
                )
                delta_lots_needed = MAX_HEDGE_LOTS * (1 if delta_lots_needed > 0 else -1) - hedge_holding

            if delta_lots_needed == 0:
                continue

            # ── 发出对冲订单（市价单）────────────────────────────
            direction = "BUY" if delta_lots_needed > 0 else "SELL"
            trade_lots = abs(delta_lots_needed)

            logger.info(
                f"[对冲] {direction} {trade_lots}手 ETF @ 市价 | "
                f"净Delta={net_delta:.0f} → 目标≈0"
            )

            # 实际下单（此处为教学演示，采用限价单贴近市价）
            limit_price = (
                quote_hedge.ask_price1 if direction == "BUY" else quote_hedge.bid_price1
            )

            pending_order = api.insert_order(
                symbol=HEDGE_SYMBOL,
                direction=direction,
                offset="OPEN" if direction == "BUY" else "CLOSE",
                volume=trade_lots,
                limit_price=limit_price,
            )

            # 等待成交（最多等 5 秒）
            deadline = datetime.datetime.now() + datetime.timedelta(seconds=5)
            while pending_order.status != "FINISHED":
                await api.wait_update()
                if datetime.datetime.now() > deadline:
                    logger.warning("[对冲] 订单超时，撤单")
                    api.cancel_order(pending_order)
                    break

            if pending_order.status == "FINISHED":
                logger.info(
                    f"[成交] {direction} {pending_order.volume_orign}手 "
                    f"@ {pending_order.trade_price:.4f}"
                )

    except KeyboardInterrupt:
        logger.info("策略手动停止")
    finally:
        api.close()
        logger.info("TqSdk 连接已关闭")


# ─── 入口 ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    运行说明：
      1. 安装依赖：pip install tqsdk
      2. 替换 TqAuth 中的用户名和密码（天勤量化账号）
      3. 确认 OPTION_CODE 为当日有效的 50ETF 期权合约代码
      4. 建议先在仿真模式（TqSim）下运行至少一周，观察对冲效果
      5. python 01_delta_hedge.py
    """
    asyncio.run(run_delta_hedge())
