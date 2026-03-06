# tqsdk-options

> 基于 **TqSdk** 的期权策略集合，持续更新中。

## 策略列表

| # | 文件 | 品种 | 策略名称 | 核心逻辑 |
|---|------|------|---------|---------|
| 01 | [01_delta_hedge.py](strategies/01_delta_hedge.py) | 50ETF期权 | Delta动态对冲策略 | 持有期权多头，动态调整标的期货对冲Delta风险 |
| 02 | [02_theta_decay_sell.py](strategies/02_theta_decay_sell.py) | 豆粕期权 | Theta时间价值卖方策略 | 卖出虚值期权收取时间价值，ATR止损管理尾部风险 |

持续更新中，欢迎 Star ⭐
