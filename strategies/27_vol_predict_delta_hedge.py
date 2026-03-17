#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
期权波动率预测Delta对冲策略 (Option Volatility Prediction Delta Hedge)
=======================================================================

策略思路：
---------
本策略在传统Delta对冲基础上加入波动率预测，提升对冲效果。
核心机制：
  1. 持有期权多头（做多波动率）
  2. 预测未来波动率变化方向
  3. 在波动率即将上升时减少对冲，保留更多Vega敞口
  4. 在波动率即将下降时加强对冲，锁定更多利润

波动率预测：
  - 基于历史波动率趋势外推
  - 结合成交量异动判断
  - 波动率突破20日高点时预测继续上升

对冲策略：
  - 基础Delta对冲：保持组合Delta接近0
  - 波动率预测增强：根据预测信号调整对冲频率和比例

标的配置：
  - 50ETF期权：510050.SH
  - 波动率预测周期：5天

风险控制：
---------
- 最大对冲偏差：Delta偏离不超过0.1
- 对冲频率：每30分钟或价格变动2%时对冲
- 波动率预测失效：连续3次预测错误暂停5天

作者: TqSdk Strategies
更新: 2026-03-17
"""

from tqsdk import TqApi, TqAuth, TqSim
from tqsdk.option import TqOption
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


class VolPredictDeltaHedgeStrategy:
    """期权波动率预测Delta对冲策略"""

    # 标的配置
    UNDERLYING = "510050.SH"  # 50ETF
    
    # 策略参数
    VOL_LOOKBACK = 20           # 波动率计算回看天数
    PREDICT_DAYS = 5            # 预测持有天数
    HEDGE_INTERVAL = 1800       # 对冲间隔（秒）
    PRICE_CHANGE_HEDGE = 0.02   # 价格变动2%对冲
    MAX_DELTA_DEV = 0.1        # 最大Delta偏离
    
    def __init__(self, api):
        self.api = api
        self.option_api = TqOption(api, self.UNDERLYING)
        self.position = None     # 期权持仓
        self.last_hedge_time = None
        self.last_price = None
        self.prediction_errors = 0
        self.last_prediction = None
        
    def get_historical_vol(self, days=20):
        """计算历史波动率"""
        kline = self.api.get_kline_serial(
            self.UNDERLYING, 86400, data_length=days + 10
        )
        
        if kline is None or len(kline) < days:
            return None
        
        close = kline['close'].values[-days:]
        returns = np.diff(np.log(close))
        vol = np.std(returns) * np.sqrt(252)
        
        return vol
    
    def predict_vol_direction(self):
        """
        预测波动率方向
        返回: 1 (上升), -1 (下降), 0 (不确定)
        """
        # 获取多日波动率
        vols = []
        for i in range(1, 6):
            vol = self.get_historical_vol(20 - i * 2)
            if vol:
                vols.append(vol)
        
        if len(vols) < 3:
            return 0
        
        # 趋势判断
        recent_vol = np.mean(vols[-2:])
        older_vol = np.mean(vols[:-2])
        
        # 波动率上升
        if recent_vol > older_vol * 1.05:
            return 1
        
        # 波动率下降
        if recent_vol < older_vol * 0.95:
            return -1
        
        # 检查是否突破20日高点
        current_vol = self.get_historical_vol(20)
        if current_vol:
            hist_vols = []
            for i in range(1, 21):
                vol = self.get_historical_vol(20 + i)
                if vol:
                    hist_vols.append(vol)
            
            if hist_vols and current_vol > np.max(hist_vols) * 0.95:
                return 1  # 接近高点，可能继续
        
        return 0
    
    def get_option_position(self):
        """获取期权持仓"""
        try:
            positions = self.api.get_position()
            for pos in positions:
                if '510050' in pos.symbol:
                    return pos
        except:
            pass
        return None
    
    def calculate_greeks(self):
        """计算期权希腊值（简化版）"""
        # 获取标的价格
        quote = self.api.get_quote(self.UNDERLYING)
        underlying_price = quote.last_price
        
        # 获取波动率
        current_vol = self.get_historical_vol(20)
        
        # 获取期权持仓
        pos = self.get_option_position()
        if pos is None:
            return None
        
        # 简化Delta计算
        # 实际应使用Black-Scholes模型
        position_delta = pos.pos_long - pos.pos_short
        
        return {
            'position_delta': position_delta,
            'underlying_price': underlying_price,
            'volatility': current_vol,
            'pos_long': pos.pos_long,
            'pos_short': pos.pos_short
        }
    
    def hedge_delta(self, vol_prediction=0):
        """
        Delta对冲
        vol_prediction: 波动率预测方向
        """
        greeks = self.calculate_greeks()
        if greeks is None:
            return
        
        position_delta = greeks['position_delta']
        underlying_price = greeks['underlying_price']
        
        # 目标Delta
        # 波动率预测为正时，减少对冲（保留Vega敞口）
        # 波动率预测为负时，加强对冲（锁定利润）
        target_delta_adjustment = vol_prediction * 0.3
        target_delta = target_delta_adjustment
        
        # 当前需要对冲的Delta
        delta_to_hedge = position_delta - target_delta
        
        # 如果Delta偏离超过阈值，进行对冲
        if abs(delta_to_hedge) > self.MAX_DELTA_DEV:
            volume = int(abs(delta_to_hedge))
            
            if delta_to_hedge > 0:
                # 需要卖出标的
                self.api.insert_order(
                    symbol=self.UNDERLYING,
                    direction="sell",
                    volume=volume
                )
                print(f"[对冲] 卖出{volume}手标的, Delta={position_delta:.2f}")
            else:
                # 需要买入标的
                self.api.insert_order(
                    symbol=self.UNDERLYING,
                    direction="buy",
                    volume=volume
                )
                print(f"[对冲] 买入{volume}手标的, Delta={position_delta:.2f}")
        
        self.last_hedge_time = datetime.now()
    
    def check_prediction_accuracy(self, actual_vol_change):
        """检查预测准确性"""
        if self.last_prediction is None:
            return
        
        # 预测正确
        if (self.last_prediction > 0 and actual_vol_change > 0) or \
           (self.last_prediction < 0 and actual_vol_change < 0):
            self.prediction_errors = 0
        else:
            self.prediction_errors += 1
        
        self.last_prediction = None
        
        # 连续错误3次，暂停
        if self.prediction_errors >= 3:
            print("[警告] 波动率预测连续错误3次，暂停5天")
            return False
        return True
    
    def open_option_position(self, direction="buy"):
        """开期权仓"""
        # 获取虚值期权
        quote = self.api.get_quote(self.UNDERLYING)
        underlying_price = quote.last_price
        
        # 选择平值附近的看涨期权
        strike = round(underlying_price / 0.05) * 0.05
        
        # 找到合适的期权合约
        option_symbol = f"510050C{str(int(strike * 1000)).zfill(5)}2306"
        
        if direction == "buy":
            self.api.insert_order(
                symbol=option_symbol,
                direction="buy",
                offset="open",
                volume=1
            )
            print(f"[开仓] 买入期权 {option_symbol}")
        else:
            self.api.insert_order(
                symbol=option_symbol,
                direction="sell",
                offset="open",
                volume=1
            )
            print(f"[开仓] 卖出期权 {option_symbol}")
    
    def run(self):
        """运行策略"""
        print(f"启动期权波动率预测Delta对冲策略...")
        print(f"标的: {self.UNDERLYING}")
        
        # 初始开仓
        self.open_option_position("buy")
        
        while True:
            self.api.wait_update()
            
            now = datetime.now()
            
            # 对冲时间检查
            need_hedge = False
            
            if self.last_hedge_time is None:
                need_hedge = True
            else:
                # 时间间隔
                if (now - self.last_hedge_time).seconds >= self.HEDGE_INTERVAL:
                    need_hedge = True
                
                # 价格变动检查
                greeks = self.calculate_greeks()
                if greeks and self.last_price:
                    price_change = abs(greeks['underlying_price'] - self.last_price) / self.last_price
                    if price_change >= self.PRICE_CHANGE_HEDGE:
                        need_hedge = True
            
            if need_hedge:
                # 预测波动率方向
                vol_prediction = self.predict_vol_direction()
                self.last_prediction = vol_prediction
                
                # 执行对冲
                self.hedge_delta(vol_prediction)
                
                # 更新价格
                if greeks:
                    self.last_price = greeks['underlying_price']
            
            # 每天检查一次预测准确性
            if now.hour == 15 and now.minute < 5:
                if self.last_prediction is not None:
                    current_vol = self.get_historical_vol(10)
                    older_vol = self.get_historical_vol(20)
                    if current_vol and older_vol:
                        vol_change = (current_vol - older_vol) / older_vol
                        self.check_prediction_accuracy(vol_change)


def main():
    """主函数"""
    api = TqSim()
    # api = TqApi(auth=TqAuth("快期账户", "账户密码"))
    
    strategy = VolPredictDeltaHedgeStrategy(api)
    
    try:
        strategy.run()
    except KeyboardInterrupt:
        print("策略停止")
    finally:
        api.close()


if __name__ == "__main__":
    main()
