#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
期权Vega对冲策略 (Vega Hedging Strategy)
========================================

策略思路：
---------
Vega衡量期权价格对波动率的敏感度。本策略通过动态调整期权仓位来对冲Vega风险，
同时获取波动率交易的收益。

实现逻辑：
---------
1. 买入跨式组合(Long Straddle)做多波动率
2. 动态卖出/买入标的资产来对冲Delta
3. 当波动率上升时获利

适用场景：
---------
- 预期标的价格将大幅波动（如重大事件前后）
- 波动率处于历史低位
- 预期波动率将上升

风险：
-----
- Theta衰减：时间价值流失
- Vega风险：波动率未如预期上升

作者: TqSdk Options
"""

from tqsdk import TqApi, TqAuth, TqSim
from tqsdk.option import TqOption
import pandas as pd
import numpy as np
from datetime import datetime


class VegaHedgeStrategy:
    """期权Vega对冲策略"""
    
    def __init__(self, api, symbol, params=None):
        """
        初始化策略
        
        Args:
            api: TqApi实例
            symbol: 标的资产代码
            params: 策略参数
        """
        self.api = api
        self.symbol = symbol
        self.params = params or {}
        
        # 策略参数
        self.strike_pct = self.params.get('strike_pct', 0.0)   # 行权价偏移(0=平值)
        self.delta_hedge_threshold = self.params.get('delta_hedge_threshold', 0.1)  # Delta对冲阈值
        self.rebalance_interval = self.params.get('rebalance_interval', 3600)  # 重新平衡间隔(秒)
        
        # 持仓
        self.call_position = {'symbol': None, 'volume': 0, 'delta': 0, 'vega': 0}
        self.put_position = {'symbol': None, 'volume': 0, 'delta': 0, 'vega': 0}
        self.underlying_position = {'volume': 0}
        
        # 状态
        self.entry_time = None
        self.last_rebalance = None
        
    def get_option_info(self, option_symbol):
        """
        获取期权信息
        
        Args:
            option_symbol: 期权代码
            
        Returns:
            dict: 期权 Greeks 和价格信息
        """
        try:
            option = self.api.get_quote(option_symbol)
            
            if option is None:
                return None
                
            # 计算隐含波动率（简化版）
            # 实际应使用 Black-Scholes 模型计算
            last_price = option.get('last_price', 0)
            vol = option.get('implied_vol', 0)  # 如果API提供
            
            # 获取希腊字母（如果API支持）
            # TqSdk 暂未直接提供Greeks，这里简化处理
            # 实际应使用 tqsdk.lib 中的 Greeks 计算
            
            # 简化：假设看涨期权的 Delta ≈ 0.5 (ATM)
            # 实际应根据标的价格和行权价计算
            return {
                'price': last_price,
                'vol': vol,
                'bid1': option.get('bid1', 0),
                'ask1': option.get('ask1', 0),
                'volume': option.get('volume', 0),
                'open_interest': option.get('open_interest', 0)
            }
            
        except Exception as e:
            print(f"获取期权信息失败: {e}")
            return None
    
    def get_atm_strike(self):
        """
        获取平值行权价
        
        Returns:
            float: 行权价
        """
        try:
            underlying = self.api.get_quote(self.symbol)
            price = underlying.get('last_price')
            
            if price is None:
                return None
                
            # 获取期权链
            option = TqOption(self.api, self.symbol)
            options = option.get_option_chain()
            
            # 找最近的到期日
            expiries = sorted(set([o.get('expire_date') for o in options]))
            if not expiries:
                return None
                
            target_expiry = expiries[0]
            target_options = [o for o in options if o.get('expire_date') == target_expiry]
            
            # 找平值期权
            calls = [o for o in target_options if o.get('option_type') == 'CALL']
            if not calls:
                return None
                
            strikes = [o.get('strike_price') for o in calls]
            atm_strike = min(strikes, key=lambda x: abs(x - price))
            
            return atm_strike
            
        except Exception as e:
            print(f"获取平值行权价失败: {e}")
            return None
    
    def open_straddle(self):
        """
        买入跨式组合（做多波动率）
        """
        strike = self.get_atm_strike()
        if strike is None:
            print("无法获取行权价")
            return False
            
        try:
            option = TqOption(self.api, self.symbol)
            options = option.get_option_chain()
            
            # 找对应行权价的看涨和看跌期权
            target_expiry = sorted(set([o.get('expire_date') for o in options]))[0]
            
            call_symbol = None
            put_symbol = None
            
            for o in options:
                if o.get('expire_date') == target_expiry and \
                   o.get('strike_price') == strike:
                    if o.get('option_type') == 'CALL':
                        call_symbol = o.get('symbol')
                    elif o.get('option_type') == 'PUT':
                        put_symbol = o.get('symbol')
            
            if call_symbol is None or put_symbol is None:
                print("找不到合适的期权合约")
                return False
                
            # 买入跨式组合
            print(f"[开仓] 买入跨式组合: strike={strike}")
            print(f"  买入看涨: {call_symbol}")
            self.api.insert_order(symbol=call_symbol, direction="BUY", offset="OPEN", volume=1)
            
            print(f"  买入看跌: {put_symbol}")
            self.api.insert_order(symbol=put_symbol, direction="BUY", offset="OPEN", volume=1)
            
            # 更新持仓
            self.call_position = {'symbol': call_symbol, 'volume': 1}
            self.put_position = {'symbol': put_symbol, 'volume': 1}
            self.entry_time = datetime.now()
            
            return True
            
        except Exception as e:
            print(f"开仓失败: {e}")
            return False
    
    def close_straddle(self):
        """
        平掉跨式组合
        """
        if self.call_position['volume'] == 0 and self.put_position['volume'] == 0:
            return
            
        print("[平仓] 平掉跨式组合")
        
        if self.call_position['volume'] > 0:
            self.api.insert_order(
                symbol=self.call_position['symbol'],
                direction="SELL",
                offset="CLOSE",
                volume=self.call_position['volume']
            )
            
        if self.put_position['volume'] > 0:
            self.api.insert_order(
                symbol=self.put_position['symbol'],
                direction="SELL",
                offset="CLOSE",
                volume=self.put_position['volume']
            )
        
        # 平掉标的资产仓位
        if self.underlying_position['volume'] != 0:
            vol = self.underlying_position['volume']
            direction = "SELL" if vol > 0 else "BUY"
            self.api.insert_order(
                symbol=self.symbol,
                direction=direction,
                offset="CLOSE",
                volume=abs(vol)
            )
        
        self.call_position = {'symbol': None, 'volume': 0}
        self.put_position = {'symbol': None, 'volume': 0}
        self.underlying_position = {'volume': 0}
    
    def calculate_delta(self):
        """
        计算组合Delta
        
        简化版：
        - ATM Call Delta ≈ 0.5
        - ATM Put Delta ≈ -0.5
        - 标的多头 Delta = 1
        
        Returns:
            float: 总Delta
        """
        # 简化计算
        call_delta = 0.5 * self.call_position['volume']
        put_delta = -0.5 * self.put_position['volume']
        underlying_delta = self.underlying_position['volume']
        
        return call_delta + put_delta + underlying_delta
    
    def hedge_delta(self):
        """
        Delta对冲：调整标的资产仓位使组合Delta接近0
        """
        total_delta = self.calculate_delta()
        
        if abs(total_delta) < self.delta_hedge_threshold:
            return
            
        print(f"[Delta对冲] 当前Delta: {total_delta:.3f}")
        
        # 需要调整的标的仓位
        hedge_volume = -int(total_delta)
        
        if hedge_volume > 0:
            # 卖出标的
            print(f"  卖出{self.symbol}: {hedge_volume}手")
            self.api.insert_order(
                symbol=self.symbol,
                direction="SELL",
                offset="OPEN",
                volume=hedge_volume
            )
        elif hedge_volume < 0:
            # 买入标的
            print(f"  买入{self.symbol}: {-hedge_volume}手")
            self.api.insert_order(
                symbol=self.symbol,
                direction="BUY",
                offset="OPEN",
                volume=-hedge_volume
            )
        
        self.underlying_position['volume'] += hedge_volume
    
    def calculate_pnl(self):
        """
        计算盈亏
        
        Returns:
            dict: 盈亏信息
        """
        pnl = 0
        
        # 期权盈亏
        if self.call_position['symbol']:
            info = self.get_option_info(self.call_position['symbol'])
            if info:
                # 简化：假设开仓价为bid1
                pnl += info.get('price', 0) * self.call_position['volume'] * 10000
                
        if self.put_position['symbol']:
            info = self.get_option_info(self.put_position['symbol'])
            if info:
                pnl += info.get('price', 0) * self.put_position['volume'] * 10000
        
        return pnl
    
    def check_exit_conditions(self):
        """
        检查平仓条件
        
        条件：
        1. 距离到期日3天以内
        2. 盈亏达到止盈/止损点
        3. 波动率大幅上升/下降
        """
        # 简化：持仓超过指定时间或达到盈亏目标
        if self.entry_time:
            hold_time = (datetime.now() - self.entry_time).total_seconds()
            
            # 持仓超过N秒平仓
            max_hold_time = 7 * 24 * 3600  # 7天
            if hold_time > max_hold_time:
                print("[平仓] 持仓超时")
                return True
        
        return False
    
    def run(self):
        """主循环"""
        print("=" * 60)
        print("期权Vega对冲策略启动")
        print(f"标的: {self.symbol}")
        print("策略: 买入跨式组合 + Delta对冲")
        print("=" * 60)
        
        # 初始开仓
        self.open_straddle()
        
        while True:
            try:
                self.api.wait_update()
                
                # 定期检查和调整
                current_time = datetime.now()
                
                if self.last_rebalance is None or \
                   (current_time - self.last_rebalance).total_seconds() > self.rebalance_interval:
                    
                    # 检查是否需要平仓
                    if self.call_position['volume'] > 0 and self.check_exit_conditions():
                        self.close_straddle()
                        break
                    
                    # Delta对冲
                    self.hedge_delta()
                    
                    # 显示状态
                    delta = self.calculate_delta()
                    print(f"\n[{current_time}] Delta: {delta:.3f}")
                    
                    self.last_rebalance = current_time
                    
            except KeyboardInterrupt:
                print("\n策略停止")
                if self.call_position['volume'] > 0:
                    self.close_straddle()
                break
            except Exception as e:
                print(f"运行错误: {e}")


def main():
    """主函数"""
    # 使用模拟账户
    api = TqApi(auth=TqAuth("YOUR_ACCOUNT", "YOUR_PASSWORD"))
    
    # 策略参数
    params = {
        'strike_pct': 0.0,                    # 平值
        'delta_hedge_threshold': 0.1,        # Delta阈值
        'rebalance_interval': 3600           # 1小时检查一次
    }
    
    # 启动策略 (50ETF期权)
    strategy = VegaHedgeStrategy(api, "510050.SH", params)
    strategy.run()


if __name__ == "__main__":
    main()
