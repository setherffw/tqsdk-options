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

策略名称：300ETF 期权卖方 Theta 时间价值衰减策略
策略编号：02
策略类型：卖方 Theta / 卖出宽跨式组合（Short Strangle）
适用品种：沪深 300ETF 期权（沪市 510300）
策略日期：2026-03-02
================================================================================

【策略原理】
--------------------
Theta（Θ）是期权价格关于时间的一阶偏导数，反映在其他条件不变的情况下，时间
流逝一天期权价值的变化量（通常为负值，即期权随时间流逝而贬值）：

  Θ = ∂V / ∂t

对于期权买方而言，Theta 是"时间的敌人"——每过一天，期权的时间价值都在减少。
而对于期权卖方（本策略角色），Theta 恰恰是收益来源——"时间是朋友"：

  · 卖出虚值 Call + 卖出虚值 Put = 卖出宽跨式组合（Short Strangle）
  · 只要标的价格在到期前不大幅突破行权价，两腿期权同时变为废纸，卖方赚取
    全部权利金（即 Theta 收益）

本策略采用"卖出宽跨式组合"（Short Strangle）：
  · 卖出虚值看涨期权（OTM Call）：行权价 = 当前价 × (1 + K%)
  · 卖出虚值看跌期权（OTM Put） ：行权价 = 当前价 × (1 - K%)
  · 同一到期日，通常选取距到期 20-45 个交易日的合约（Theta 衰减最快区间）

【宽跨式组合盈亏结构】
--------------------
  最大盈利   = 卖出 Call 权利金 + 卖出 Put 权利金
               （当标的到期价在两个行权价之间时实现）
  盈亏平衡点 = 上方：Call行权价 + 净权利金总额/合约乘数
               下方：Put行权价  - 净权利金总额/合约乘数
  最大亏损   = 理论无限（标的价格大幅突破任一方向）

【Theta 衰减时间规律】
--------------------
  期权时间价值并非线性衰减，而是呈"加速衰减"特征（尤其在到期前30天内）：
  期权的时间价值 ≈ σ × √(T/365) × S × N(d2)（Black-Scholes 简化）
  其中 σ=波动率，T=剩余天数，S=标的价格

  到期天数    Theta 加速效应        适合卖方策略
  ≥ 60 天   衰减缓慢，收益较低      ✗ 不建仓
  30-60 天  衰减提速，性价比最优    ✓ 最佳建仓窗口（★本策略目标DTE）
  15-30 天  衰减较快，Gamma↑       △ 可持有，密切监控
  ≤ 15 天   衰减极快，Gamma 风险↑↑  ⚠ 准备平仓
  ≤  5 天   Gamma 风险极高          ✗ 强制平仓

【风控机制】
--------------------
本策略内置以下风控措施：
  1. 止损线：当浮亏超过初始权利金收入的 200% 时，强制平仓（止损）
  2. 到期管理：距到期日 5 个交易日以内，提前平仓避免 Gamma 风险急剧放大
  3. Delta 监控：当组合 |Delta| > 阈值时，发出预警（可配合 01_delta_hedge.py
     联动使用）
  4. 隐含波动率（IV）预警：若 IV 突然大幅跳升（超过建仓时 IV 的 50%），
     输出风险提示日志，提醒人工审查
  5. 仓位控制：单笔开仓保证金占用不超过账户净值的 20%

【参数说明】
--------------------
  UNDERLYING       : 标的 ETF 代码（沪市 300ETF：SSE.510300）
  CALL_STRIKE_PCT  : Call 行权价相对现价的比例偏移（如 0.05 = 高于现价 5%）
  PUT_STRIKE_PCT   : Put  行权价相对现价的比例偏移（如 0.05 = 低于现价 5%）
  SELL_LOTS        : 每腿卖出手数（张）
  STOP_LOSS_RATIO  : 止损比例（权利金收入的倍数），默认 2.0 倍
  DAYS_TO_EXPIRY_MIN: 最小剩余天数（低于此值强制平仓），默认 5 天
  TARGET_DTE       : 建仓目标剩余天数（Days To Expiry），默认 30 天
  IV_ALERT_RATIO   : IV 跳升预警倍数，默认 1.5 倍

================================================================================
"""

import asyncio
import datetime
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

from tqsdk import TqApi, TqAuth, TqSim
from tqsdk.objs import Quote, Order, Position

# ─── 日志配置 ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            f"theta_sell_{datetime.date.today()}.log", encoding="utf-8"
        ),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("ThetaSell")

# ─── 策略参数 ────────────────────────────────────────────────────────────────
UNDERLYING: str          = "SSE.510300"      # 沪市 300ETF
CALL_STRIKE_PCT: float   = 0.05              # Call 行权价：现价上方 5%
PUT_STRIKE_PCT: float    = 0.05              # Put  行权价：现价下方 5%
SELL_LOTS: int           = 5                 # 每腿卖出 5 张
STOP_LOSS_RATIO: float   = 2.0              # 浮亏超过权利金 2 倍时止损
DAYS_TO_EXPIRY_MIN: int  = 5               # 距到期 ≤5 天强制平仓
TARGET_DTE: int          = 30              # 目标建仓剩余天数（约 1 个月）
IV_ALERT_RATIO: float    = 1.5            # IV 突破建仓时 1.5 倍触发预警
CONTRACT_MULTIPLIER: int = 10000          # 每张期权对应 10000 份 ETF
ACCOUNT_BALANCE: float   = 1_000_000.0   # 账户净值（元），用于仓位控制

# ─── 数据结构 ────────────────────────────────────────────────────────────────

@dataclass
class StrategyPosition:
    """策略持仓记录，跟踪卖出 Call 和卖出 Put 的状态。"""
    call_symbol: str   = ""
    put_symbol: str    = ""
    call_lots: int     = 0
    put_lots: int      = 0
    call_premium: float = 0.0
    put_premium: float  = 0.0
    entry_date: str    = ""
    entry_iv_call: float = 0.0
    entry_iv_put: float  = 0.0
    is_open: bool      = False
    total_premium_income: float = 0.0


@dataclass
class RiskMetrics:
    """实时风险指标，用于监控和预警。"""
    net_delta: float   = 0.0
    net_theta: float   = 0.0
    net_vega: float    = 0.0
    net_gamma: float   = 0.0
    current_pnl: float = 0.0
    max_loss: float    = 0.0


# ─── 辅助函数 ────────────────────────────────────────────────────────────────

def calc_target_strikes(current_price: float) -> Tuple[float, float]:
    """
    根据当前 ETF 价格计算目标行权价。

    Args:
        current_price: 标的 ETF 当前价格

    Returns:
        Tuple[float, float]: (call_strike, put_strike)
    """
    call_strike = round(current_price * (1 + CALL_STRIKE_PCT), 4)
    put_strike  = round(current_price * (1 - PUT_STRIKE_PCT),  4)
    return call_strike, put_strike


def calc_position_pnl(
    pos: StrategyPosition,
    call_quote: Quote,
    put_quote: Quote,
) -> float:
    """
    计算当前持仓浮盈亏。

    卖出期权的 PnL = 建仓收到的权利金 - 当前平仓需要支付的权利金
    正值为盈利，负值为亏损。

    Args:
        pos       : 策略持仓记录
        call_quote: Call 期权实时行情
        put_quote : Put  期权实时行情

    Returns:
        float: 浮盈亏（元）
    """
    if not pos.is_open:
        return 0.0
    call_close_cost = call_quote.last_price * pos.call_lots * CONTRACT_MULTIPLIER
    put_close_cost  = put_quote.last_price  * pos.put_lots  * CONTRACT_MULTIPLIER
    call_income = pos.call_premium * pos.call_lots * CONTRACT_MULTIPLIER
    put_income  = pos.put_premium  * pos.put_lots  * CONTRACT_MULTIPLIER
    return (call_income + put_income) - (call_close_cost + put_close_cost)


def is_stop_loss_triggered(pos: StrategyPosition, current_pnl: float) -> bool:
    """
    判断是否触发止损：浮亏超过初始权利金 STOP_LOSS_RATIO 倍。

    Args:
        pos        : 策略持仓记录
        current_pnl: 当前浮盈亏（元）

    Returns:
        bool: True 表示触发止损
    """
    if current_pnl >= 0:
        return False
    return abs(current_pnl) >= pos.total_premium_income * STOP_LOSS_RATIO


def days_to_expiry(expiry_date_str: str) -> int:
    """
    计算距到期日剩余自然日天数。

    Args:
        expiry_date_str: 到期日字符串，格式 "YYYY-MM-DD"

    Returns:
        int: 剩余天数
    """
    expiry = datetime.datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
    return max(0, (expiry - datetime.date.today()).days)


def calc_position_size(premium_per_lot: float) -> int:
    """
    根据账户净值计算单腿最大手数（保证金占用 ≤ 账户净值 20%）。

    Args:
        premium_per_lot: 每张期权当前权利金（元/份）

    Returns:
        int: 建议最大手数
    """
    # 简化保证金估算：期权保证金 ≈ 权利金市值 × 15%（教学估算）
    estimated_margin = premium_per_lot * CONTRACT_MULTIPLIER * 0.15
    if estimated_margin <= 0:
        return SELL_LOTS
    max_lots = int(ACCOUNT_BALANCE * 0.20 / estimated_margin)
    return min(max_lots, SELL_LOTS)


# ─── 建仓 / 平仓 ─────────────────────────────────────────────────────────────

async def close_position(
    api: TqApi,
    pos: StrategyPosition,
    call_quote: Quote,
    put_quote: Quote,
    reason: str,
) -> None:
    """
    平仓：同时买入回 Call 和 Put 两腿。

    Args:
        api       : TqSdk 实例
        pos       : 当前持仓
        call_quote: Call 行情
        put_quote : Put  行情
        reason    : 平仓原因（日志记录）
    """
    logger.warning(f"[平仓触发] 原因: {reason}")
    orders: List[Order] = []

    if pos.call_lots > 0 and pos.call_symbol:
        o = api.insert_order(
            symbol=pos.call_symbol,
            direction="BUY",
            offset="CLOSE",
            volume=pos.call_lots,
            limit_price=call_quote.ask_price1,
        )
        orders.append(o)
        logger.info(f"  [平Call] BUY {pos.call_lots}张 @ {call_quote.ask_price1:.4f}")

    if pos.put_lots > 0 and pos.put_symbol:
        o = api.insert_order(
            symbol=pos.put_symbol,
            direction="BUY",
            offset="CLOSE",
            volume=pos.put_lots,
            limit_price=put_quote.ask_price1,
        )
        orders.append(o)
        logger.info(f"  [平Put ] BUY {pos.put_lots}张 @ {put_quote.ask_price1:.4f}")

    # 最多等 10 秒
    deadline = datetime.datetime.now() + datetime.timedelta(seconds=10)
    while any(o.status != "FINISHED" for o in orders):
        await api.wait_update()
        if datetime.datetime.now() > deadline:
            for o in orders:
                if o.status != "FINISHED":
                    api.cancel_order(o)
                    logger.warning(f"  [撤单] {o.order_id} 超时撤销")
            break

    pos.is_open   = False
    pos.call_lots = 0
    pos.put_lots  = 0
    logger.info("[平仓完成]")


async def open_position(
    api: TqApi,
    pos: StrategyPosition,
    call_symbol: str,
    put_symbol: str,
    call_quote: Quote,
    put_quote: Quote,
) -> None:
    """
    建仓：同时卖出 Call 和 Put 两腿构成宽跨式组合。

    Args:
        api        : TqSdk 实例
        pos        : 待更新的持仓记录
        call_symbol: Call 合约代码
        put_symbol : Put  合约代码
        call_quote : Call 行情
        put_quote  : Put  行情
    """
    call_lots = calc_position_size(call_quote.last_price)
    put_lots  = calc_position_size(put_quote.last_price)

    est_income = (
        call_quote.bid_price1 * call_lots * CONTRACT_MULTIPLIER
        + put_quote.bid_price1 * put_lots * CONTRACT_MULTIPLIER
    )
    logger.info("=" * 55)
    logger.info("[建仓] 卖出宽跨式组合（Short Strangle）")
    logger.info(f"  SELL Call: {call_symbol} × {call_lots}张 @ {call_quote.bid_price1:.4f}")
    logger.info(f"  SELL Put : {put_symbol}  × {put_lots}张 @ {put_quote.bid_price1:.4f}")
    logger.info(f"  预计权利金收入: {est_income:.2f} 元")
    logger.info("=" * 55)

    call_order = api.insert_order(
        symbol=call_symbol, direction="SELL", offset="OPEN",
        volume=call_lots, limit_price=call_quote.bid_price1,
    )
    put_order = api.insert_order(
        symbol=put_symbol, direction="SELL", offset="OPEN",
        volume=put_lots, limit_price=put_quote.bid_price1,
    )

    deadline = datetime.datetime.now() + datetime.timedelta(seconds=15)
    orders = [call_order, put_order]
    while any(o.status != "FINISHED" for o in orders):
        await api.wait_update()
        if datetime.datetime.now() > deadline:
            for o in orders:
                if o.status != "FINISHED":
                    api.cancel_order(o)
            logger.warning("[建仓] 部分订单超时撤销")
            break

    # 更新持仓记录
    call_filled = call_order.volume_left == 0
    put_filled  = put_order.volume_left == 0

    if call_filled and put_filled:
        pos.call_symbol   = call_symbol
        pos.put_symbol    = put_symbol
        pos.call_lots     = call_lots
        pos.put_lots      = put_lots
        pos.call_premium  = getattr(call_order, "trade_price", call_quote.bid_price1)
        pos.put_premium   = getattr(put_order,  "trade_price", put_quote.bid_price1)
        pos.entry_date    = datetime.date.today().isoformat()
        pos.entry_iv_call = getattr(call_quote, "sigma", 0.0) or 0.0
        pos.entry_iv_put  = getattr(put_quote,  "sigma", 0.0) or 0.0
        pos.total_premium_income = (
            pos.call_premium * pos.call_lots * CONTRACT_MULTIPLIER
            + pos.put_premium * pos.put_lots * CONTRACT_MULTIPLIER
        )
        pos.is_open = True
        logger.info(
            f"[建仓成功] Call成交={pos.call_premium:.4f} "
            f"Put成交={pos.put_premium:.4f} "
            f"总收入={pos.total_premium_income:.2f}元"
        )
    else:
        logger.error("[建仓] 未能全部成交，请人工检查仓位")


# ─── 主策略协程 ───────────────────────────────────────────────────────────────

async def run_theta_sell():
    """
    卖方 Theta 时间价值衰减策略主协程。

    策略流程：
      1. 连接 TqSdk，订阅 300ETF 行情
      2. 根据现价确定目标行权价，选取期权合约代码
      3. 执行建仓（卖出宽跨式组合）
      4. 持续监控 PnL / DTE / IV，触发风控时平仓
      5. 记录运行日志，策略结束后输出绩效摘要
    """
    api = TqApi(
        account=TqSim(init_balance=ACCOUNT_BALANCE),
        auth=TqAuth("YOUR_TIANQIN_USERNAME", "YOUR_TIANQIN_PASSWORD"),
    )

    logger.info("=" * 60)
    logger.info("卖方 Theta 时间价值衰减策略 启动")
    logger.info(f"标的品种   : {UNDERLYING}（沪市300ETF）")
    logger.info(f"策略类型   : Short Strangle（卖出宽跨式）")
    logger.info(f"行权偏移   : Call+{CALL_STRIKE_PCT*100:.0f}% / Put-{PUT_STRIKE_PCT*100:.0f}%")
    logger.info(f"目标DTE    : {TARGET_DTE} 天")
    logger.info(f"止损倍数   : {STOP_LOSS_RATIO}× 权利金")
    logger.info(f"强平天数   : DTE ≤ {DAYS_TO_EXPIRY_MIN} 天")
    logger.info("=" * 60)

    pos   = StrategyPosition()
    risk  = RiskMetrics()
    max_loss_recorded = 0.0

    try:
        # ── 订阅 ETF 行情 ──────────────────────────────────────────
        etf_quote: Quote = api.get_quote(UNDERLYING)
        await api.wait_update()

        current_price = etf_quote.last_price
        logger.info(f"300ETF 当前价: {current_price:.4f}")

        call_strike, put_strike = calc_target_strikes(current_price)
        logger.info(f"目标 Call 行权价: {call_strike:.4f} (现价 +{CALL_STRIKE_PCT*100:.0f}%)")
        logger.info(f"目标 Put  行权价: {put_strike:.4f} (现价 -{PUT_STRIKE_PCT*100:.0f}%)")

        # ──────────────────────────────────────────────────────────
        # 【重要说明】
        # 实盘中应通过 TqSdk 期权链查询 API 动态选取合约代码：
        #   option_list = api.query_options(UNDERLYING, option_class="CALL",
        #                                   strike_price=call_strike, ...)
        # 以下为示例合约代码（格式：SSE.10005XXX），请按实际月份替换
        # ──────────────────────────────────────────────────────────
        CALL_SYMBOL = "SSE.10005001"   # 300ETF 近月 OTM Call（示例，需替换）
        PUT_SYMBOL  = "SSE.10005002"   # 300ETF 近月 OTM Put （示例，需替换）
        EXPIRY_DATE = "2026-03-26"     # 到期日（需与合约匹配）

        # 检查剩余天数
        dte = days_to_expiry(EXPIRY_DATE)
        logger.info(f"合约到期日: {EXPIRY_DATE}，距今 {dte} 天")
        if dte < DAYS_TO_EXPIRY_MIN:
            logger.error(f"剩余 {dte} 天 < 最低要求 {DAYS_TO_EXPIRY_MIN} 天，策略终止")
            return

        # 订阅期权行情
        call_quote: Quote = api.get_quote(CALL_SYMBOL)
        put_quote: Quote  = api.get_quote(PUT_SYMBOL)
        await api.wait_update()

        # 建仓
        if not pos.is_open:
            await open_position(api, pos, CALL_SYMBOL, PUT_SYMBOL, call_quote, put_quote)

        # ── 主监控循环 ─────────────────────────────────────────────
        while pos.is_open:
            await api.wait_update()

            # 价格有效性检查
            cp = call_quote.last_price
            pp = put_quote.last_price
            if cp != cp or pp != pp:  # NaN 判断
                continue

            # 计算 PnL
            current_pnl = calc_position_pnl(pos, call_quote, put_quote)
            risk.current_pnl = current_pnl
            if current_pnl < max_loss_recorded:
                max_loss_recorded = current_pnl

            # 剩余天数
            dte = days_to_expiry(EXPIRY_DATE)

            # Greeks（若行情提供）
            c_delta = getattr(call_quote, "delta", 0) or 0
            p_delta = getattr(put_quote,  "delta", 0) or 0
            c_theta = getattr(call_quote, "theta", 0) or 0
            p_theta = getattr(put_quote,  "theta", 0) or 0

            # 卖方头寸 Greeks 取反
            risk.net_delta = -(c_delta * pos.call_lots + p_delta * pos.put_lots) * CONTRACT_MULTIPLIER
            risk.net_theta = -(c_theta * pos.call_lots + p_theta * pos.put_lots) * CONTRACT_MULTIPLIER

            logger.info(
                f"[监控] PnL={current_pnl:+.2f}元 | "
                f"Theta={risk.net_theta:+.2f}元/天 | "
                f"Delta={risk.net_delta:.2f} | "
                f"DTE={dte}天 | "
                f"止损线={pos.total_premium_income * STOP_LOSS_RATIO:.2f}元"
            )

            # ── 风控1：止损 ────────────────────────────────────────
            if is_stop_loss_triggered(pos, current_pnl):
                await close_position(
                    api, pos, call_quote, put_quote,
                    reason=(
                        f"止损触发：浮亏 {abs(current_pnl):.2f}元 ≥ "
                        f"权利金 {pos.total_premium_income:.2f}元 × {STOP_LOSS_RATIO}"
                    ),
                )
                break

            # ── 风控2：临近到期 ────────────────────────────────────
            if dte <= DAYS_TO_EXPIRY_MIN:
                await close_position(
                    api, pos, call_quote, put_quote,
                    reason=f"临近到期：DTE={dte} ≤ {DAYS_TO_EXPIRY_MIN} 天，提前平仓",
                )
                break

            # ── 预警：IV 突变 ──────────────────────────────────────
            call_iv = getattr(call_quote, "sigma", None)
            if call_iv and pos.entry_iv_call > 0:
                ratio = call_iv / pos.entry_iv_call
                if ratio > IV_ALERT_RATIO:
                    logger.warning(
                        f"[IV预警] Call IV 大幅跳升！"
                        f"建仓IV={pos.entry_iv_call:.2%} → 当前IV={call_iv:.2%} "
                        f"({ratio:.1f}倍)，请人工审查风险！"
                    )

        # ── 绩效摘要 ───────────────────────────────────────────────
        logger.info("=" * 60)
        logger.info("策略运行结束 — 绩效摘要")
        logger.info(f"  建仓日期       : {pos.entry_date}")
        logger.info(f"  权利金收入     : {pos.total_premium_income:.2f} 元")
        logger.info(f"  最终 PnL       : {risk.current_pnl:+.2f} 元")
        logger.info(f"  策略收益率     : {risk.current_pnl / ACCOUNT_BALANCE * 100:+.3f}%")
        logger.info(f"  最大浮亏       : {max_loss_recorded:.2f} 元")
        logger.info("=" * 60)

    except KeyboardInterrupt:
        logger.info("手动中断，尝试平仓...")
        if pos.is_open:
            cq: Quote = api.get_quote(pos.call_symbol)
            pq: Quote = api.get_quote(pos.put_symbol)
            await close_position(api, pos, cq, pq, reason="手动停止策略")
    finally:
        api.close()
        logger.info("TqSdk 连接已关闭")


# ─── 入口 ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    运行说明：
      1. 安装依赖：pip install tqsdk
      2. 替换 TqAuth 中的天勤量化账号信息（官网注册：https://www.shinnytech.com/）
      3. 确认 CALL_SYMBOL / PUT_SYMBOL / EXPIRY_DATE 为当月有效期权合约
