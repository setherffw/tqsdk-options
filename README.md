# tqsdk-options

> 基于 [TqSdk 天勤量化](https://github.com/shinnytech/tqsdk-python) 的期权策略集合

[![TqSdk](https://img.shields.io/badge/TqSdk-powered-blue)](https://doc.shinnytech.com/tqsdk/latest/)
[![Python](https://img.shields.io/badge/Python-3.8%2B-brightgreen)](https://www.python.org/)

---

## 📌 项目简介

本仓库收录使用 **TqSdk** 实现的期权量化策略，涵盖 Delta 对冲、卖方 Theta、Gamma Scalping、波动率套利等方向。

适用品种：**50ETF 期权**、**300ETF 期权**、**商品期权**（铜/白糖/豆粕）

---

## 📚 TqSdk 资源

| 资源 | 链接 |
|------|------|
| 官方文档 | https://doc.shinnytech.com/tqsdk/latest/ |
| GitHub | https://github.com/shinnytech/tqsdk-python |

安装：`pip install tqsdk`

---

## 📂 策略列表

| 编号 | 文件名 | 策略类型 | 品种 | 方向 | 上传日期 |
|:----:|--------|----------|------|------|----------|
| 01 | [01_delta_hedge.py](strategies/01_delta_hedge.py) | Delta 动态对冲 | 50ETF 期权 | 中性 | 2026-03-02 |
| 02 | [02_theta_decay_sell.py](strategies/02_theta_decay_sell.py) | 卖方 Theta / Short Strangle | 300ETF 期权 | 卖方 | 2026-03-02 |

---

## 🚀 快速开始

```bash
pip install tqsdk
python strategies/01_delta_hedge.py
python strategies/02_theta_decay_sell.py
```

> ⚠️ **风险提示**：本仓库策略仅供学习研究，不构成任何投资建议。实盘前请充分测试。

---

## 📋 代码规范

- ✅ 文件头包含 TqSdk 介绍段（官网 + GitHub）
- ✅ 500字以上中文注释（原理/参数/风险）
- ✅ 完整可运行的 TqSdk 代码
- ✅ 内置风控机制

---

MIT License © 2026 setherffw
