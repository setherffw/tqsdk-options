# tqsdk-options

> 基于 **TqSdk** 的期权策略集合，持续更新中。

## 项目简介

本仓库专注于**期权量化策略**，涵盖期权定价、对冲、波动率交易、组合策略等方向。  
所有策略使用 [天勤量化 TqSdk](https://github.com/shinnytech/tqsdk-python) 实现，可直接对接实盘账户。

## 策略列表

| # | 策略名称 | 类型 | 标的 | 文件 |
|---|---------|------|------|------|
| 01 | 50ETF 期权 Delta 动态对冲策略 | Delta对冲 | 510050.SH | [01_delta_hedge.py](strategies/01_delta_hedge.py) |
| 02 | 300ETF 期权卖方 Theta 时间价值衰减策略 | Theta套利 | 510300.SH | [02_theta_decay_sell.py](strategies/02_theta_decay_sell.py) |
| 03 | 波动率曲面套利策略 | 波动率套利 | 510050.SH | [03_vol_surface_arb.py](strategies/03_vol_surface_arb.py) |
| 04 | 铁鹰式期权组合策略 | 组合策略 | 510050.SH | [04_iron_condor.py](strategies/04_iron_condor.py) |
| 05 | 波动率套利：跨式组合做多波动率策略 | 波动率交易 | 510050.SH | [05_volatility_straddle.py](strategies/05_volatility_straddle.py) |
| 06 | 垂直价差：牛市价差组合策略 | 价差策略 | 510050.SH | [06_bull_vertical_spread.py](strategies/06_bull_vertical_spread.py) |
| 07 | 波动率交易：波动率价差策略 | 波动率交易 | 510050.SH | [07_volatility_spread.py](strategies/07_volatility_spread.py) |
| 08 | 垂直价差：熊市价差组合策略 | 价差策略 | 510050.SH | [08_bear_put_spread.py](strategies/08_bear_put_spread.py) |
| 09 | 看跌期权比率价差策略 | 比率价差 | 510050.SH | [09_put_ratio_spread.py](strategies/09_put_ratio_spread.py) |
| 10 | 风险逆转策略 | 风险逆转 | 510050.SH | [10_risk_reversal.py](strategies/10_risk_reversal.py) |
| 11 | 波动率交易策略 | 波动率交易 | 510050.SH | [11_volatility_trading.py](strategies/11_volatility_trading.py) |
| 12 | 备兑看涨期权策略 | 备兑策略 | 510050.SH | [12_covered_call.py](strategies/12_covered_call.py) |
| 13 | 期权日历价差策略 | 日历价差 | 510050.SH | [13_calendar_spread.py](strategies/13_calendar_spread.py) |
| 14 | 期权波动率交易策略 | 波动率交易 | 510050.SH | [14_volatility_trading.py](strategies/14_volatility_trading.py) |
| 15 | 期权Delta中性对冲策略 | Delta对冲 | 510050.SH | [15_delta_neutral_hedge.py](strategies/15_delta_neutral_hedge.py) |
| 16 | 期权时间价值套利策略 | Theta套利 | 510050.SH | [16_theta_arb.py](strategies/16_theta_arb.py) |
| 17 | 期权波动率突破策略 | 波动率突破 | 510050.SH | [17_vol_breakout.py](strategies/17_vol_breakout.py) |
| 18 | 期权保护性看跌策略 | 保护性看跌 | 510050.SH | [18_protective_put.py](strategies/18_protective_put.py) |
| 19 | 期权保护性看跌策略 | 保护性看跌 | 510050.SH | [19_protective_put.py](strategies/19_protective_put.py) |
| 20 | 期权牛市价差策略 | 价差策略 | 510050.SH | [20_bull_spread.py](strategies/20_bull_spread.py) |
| 21 | 期权蝴蝶价差策略 | 组合策略 | 510050.SH | [21_butterfly_spread.py](strategies/21_butterfly_spread.py) |
| 22 | 期权Vega对冲策略 | 波动率对冲 | 510050.SH | [22_vega_hedge.py](strategies/22_vega_hedge.py) |
| 23 | 多因子IV截面选择策略（IV Rank+PCR+期限结构） | 多因子截面 | 510050.SH | [23_multi_factor_iv_cross_section.py](strategies/23_multi_factor_iv_cross_section.py) |
| 24 | 跨标的期权对冲组合策略（50ETF/300ETF波动率价差） | 跨标的IV价差 | 510050.SH + 510300.SH | [24_cross_etf_vol_hedge.py](strategies/24_cross_etf_vol_hedge.py) |
| 25 | 期权Gamma Scalping策略 | Gamma交易 | 510050.SH | [25_gamma_scalping.py](strategies/25_gamma_scalping.py) |
| 26 | 期权期限结构套利策略 | 期限结构套利 | 510050.SH | [26_term_structure_arb.py](strategies/26_term_structure_arb.py) |
| 27 | 期权波动率预测Delta对冲策略 | Delta对冲 | 510050.SH | [27_vol_predict_delta_hedge.py](strategies/27_vol_predict_delta_hedge.py) |
| 28 | 期权波动率微笑套利策略 | 波动率套利 | 510050.SH | [28_vol_smile_arbitrage.py](strategies/28_vol_smile_arbitrage.py) |
| 29 | 波动率期限结构套利策略 | 期限结构套利 | DCE.m（豆粕） | [29_vol_term_structure_arb.py](strategies/29_vol_term_structure_arb.py) |
| 30 | 波动率偏度反转套利策略 | 偏度反转套利 | SHFE.cu（铜） | [30_vol_skew_reversal_arb.py](strategies/30_vol_skew_reversal_arb.py) |
| 31 | 期权希腊值动态风控策略 | Greeks风控 | 510050.SH | [31_greeks_risk_management.py](strategies/31_greeks_risk_management.py) |
| 32 | 期权箱式价差套利策略 | 箱式套利 | 510050.SH | [32_box_spread_arb.py](strategies/32_box_spread_arb.py) |
| 33 | 期权波动率偏度交易策略 | 波动率偏度交易 | 510050.SH | [33_volatility_skew_trading.py](strategies/33_volatility_skew_trading.py) |
| 34 | 期权希腊值风险平价组合策略 | Greeks风险平价 | 510050.SH | [34_greeks_risk_parity_portfolio.py](strategies/34_greeks_risk_parity_portfolio.py) |
| 35 | 期权隐含波动率曲面预测与动态对冲策略 | IV预测+Delta对冲 | 510050.SH | [35_iv_surface_prediction_hedging.py](strategies/35_iv_surface_prediction_hedging.py) |
| 36 | 波动率偏度微笑与期限结构套利策略 | Skew+期限结构套利 | 510050.SH | [36_vol_skew_term_structure_arb.py](strategies/36_vol_skew_term_structure_arb.py) |
| 37 | 波动率曲面预测Alpha策略 | 波动率曲面、skew、term structure、Alpha因子 | 期权波动率交易 | [37_vol_surface_alpha.py](strategies/37_vol_surface_alpha.py) |
| 38 | 期权希腊字母风险平价组合策略 | Delta/Gamma/Theta/Vega风险平价、对冲、再平衡 | 期权组合管理 | [38_greeks_risk_parity_portfolio.py](strategies/38_greeks_risk_parity_portfolio.py) |

## 策略分类

### 🎯 Delta 对冲（Delta Hedging）
通过动态调整仓位保持 Delta 中性，消除方向性风险。

### ⏰ Theta 套利（Theta Decay）
利用时间价值衰减特性，卖出期权赚取 Theta 收益。

### 📈 波动率交易（Volatility Trading）
基于波动率预期进行交易，如跨式组合、宽跨式组合等。

### 🔀 价差策略（Vertical Spreads）
垂直价差、比率价差、日历价差等组合策略。

### 🛡️ 保护性策略（Protective Strategies）
保护性看跌期权、备兑看涨期权等。

### 🧮 多因子截面策略（Multi-Factor Cross-Section）
结合IV Rank、PCR情绪因子、期限结构因子综合打分，截面选择最优期权方向。

### 🔗 跨标的IV价差策略（Cross-Asset Vol Spread）
利用不同ETF期权之间的隐含波动率相对价值，做多低估IV、做空高估IV，双腿对冲风险。

## 环境要求

```bash
pip install tqsdk numpy pandas scipy
```

## 使用说明

1. 替换代码中 `YOUR_ACCOUNT` / `YOUR_PASSWORD` 为你的天勤账号
2. 根据实际行情调整合约代码和行权价
3. 建议先用模拟账户（`TqSim()`）回测后再上实盘

## 风险提示

- 期权策略风险较高，请充分理解期权定价原理
- 波动率交易可能面临 Vega 风险
- 请充分测试后再使用于实盘
- 本仓库策略仅供学习研究，不构成投资建议

---

**持续更新中，欢迎 Star ⭐ 关注**

*更新时间：2026-03-24*
