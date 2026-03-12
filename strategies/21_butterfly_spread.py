#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
期权蝴蝶价差策略 (Butterfly Spread Strategy)
============================================

策略思路：
---------
蝴蝶价差是一种中性期权组合策略，通过三个行权价的期权组合来获得收益。
当标的价格接近中间行权价时获得最大收益。

组合构成（以看涨期权为例）：
- 买入1份低行权价看涨期权 (K1)
- 卖出2份中间行权价看涨期权 (K2)
- 买入1份高行权价看涨期权 (K3)
其中 K2 = (K1 + K3) / 2

盈亏特点：
- 标的价格接近K2时盈利最大
- 标的价格远离K1或K3时亏损有限（最大为净权利金）

作者: TqSdk Options
"""

from tqsdk import TqApi, TqAuth, TqSim
from tqsdk.option import TqOption
import pandas as pd
from datetime import datetime


class ButterflySpreadStrategy:
    """期权蝴蝶价差策略"""
    
    def __init__(self, api, symbol, params=None):
        """
        初始化策略
        
        Args:
            api: TqApi实例
            symbol: 标的资产代码 (如 510050.SH)
            params: 策略参数
        """
        self.api = api
        self.symbol = symbol
        self.params = params or {}
        
        # 策略参数
        self.option_type = self.params.get('option_type', 'call')  # 'call' 或 'put'
        self.days_to_expiry = self.params.get('days_to_expiry', 30) # 距离到期天数
        self.k_range = self.params.get('k_range', 0.05)            # 行权价间距(标的价格的百分比)
        
        # 持仓
        self.legs = []  # 期权腿列表
        
    def get_option_chain(self):
        """
        获取期权链
        
        Returns:
            dict: 期权信息
        """
        try:
            option = TqOption(self.api, self.symbol)
            
            # 获取标的价格
            underlying = self.api.get_quote(self.symbol)
            underlying_price = underlying.get('last_price')
            
            if underlying_price is None:
                return None
                
            # 获取期权链
            options = option.get_option_chain()
            
            # 筛选近月合约
            expiries = sorted(set([o.get('expire_date') for o in options]))
            if not expiries:
                return None
                
            # 选择最近的到期日
            target_expiry = expiries[0]
            
            # 筛选该到期日的期权
            target_options = [o for o in options if o.get('expire_date') == target_expiry]
            
            # 按行权价排序
            if self.option_type == 'call':
                calls = sorted([o for o in target_options if o.get('option_type') == 'CALL'], 
                              key=lambda x: x.get('strike_price', 0))
            else:
                calls = sorted([o for o in target_options if o.get('option_type') == 'PUT'], 
                              key=lambda x: x.get('strike_price', 0))
            
            return {
                'underlying_price': underlying_price,
                'expiry': target_expiry,
                'options': calls
            }
            
        except Exception as e:
            print(f"获取期权链失败: {e}")
            return None
    
    def select_strikes(self, chain):
        """
        选择三个行权价
        
        Args:
            chain: 期权链信息
            
        Returns:
            tuple: (K1, K2, K3) 三个行权价
        """
        underlying_price = chain['underlying_price']
        options = chain['options']
        
        if not options:
            return None
        
        # 找到最接近标的价格的行权价
        strikes = [o.get('strike_price') for o in options]
        nearest_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - underlying_price))
        
        # 确保有足够的行权价可选
        if nearest_idx < 1 or nearest_idx >= len(strikes) - 1:
            return None
            
        # 选择三个行权价：低、中、高
        k1 = strikes[nearest_idx - 1]  # 低价
        k2 = strikes[nearest_idx]       # 中价
        k3 = strikes[nearest_idx + 1]  # 高价
        
        return (k1, k2, k3)
    
    def build_butterfly(self, k1, k2, k3):
        """
        构建蝴蝶价差
        
        Args:
            k1, k2, k3: 三个行权价
            
        Returns:
            list: 期权腿列表
        """
        if self.option_type == 'call':
            # 买入看涨蝶式
            # 买入1份K1，卖出2份K2，买入1份K3
            legs = [
                {'strike': k1, 'action': 'BUY', 'type': 'CALL', 'volume': 1},
                {'strike': k2, 'action': 'SELL', 'type': 'CALL', 'volume': 2},
                {'strike': k3, 'action': 'BUY', 'type': 'CALL', 'volume': 1}
            ]
        else:
            # 买入看跌蝶式
            legs = [
                {'strike': k1, 'action': 'BUY', 'type': 'PUT', 'volume': 1},
                {'strike': k2, 'action': 'SELL', 'type': 'PUT', 'volume': 2},
                {'strike': k3, 'action': 'BUY', 'type': 'PUT', 'volume': 1}
            ]
            
        self.legs = legs
        return legs
    
    def open_position(self, legs):
        """
        开仓
        
        Args:
            legs: 期权腿列表
        """
        print(f"[开仓] 构建{self.option_type.upper()}蝴蝶价差: ", end="")
        for leg in legs:
            print(f"{leg['action']}{leg['volume']}手 {leg['type']}@{leg['strike']}", end=" ")
            
            # 构建期权代码
            expiry = self.get_expiry_code()
            option_symbol = f"{self.symbol}{expiry}{leg['type'][0]}{int(leg['strike']*1000):08d}"
            
            if leg['action'] == 'BUY':
                self.api.insert_order(
                    symbol=option_symbol,
                    direction="BUY",
                    offset="OPEN",
                    volume=leg['volume']
                )
            else:
                self.api.insert_order(
                    symbol=option_symbol,
                    direction="SELL",
                    offset="OPEN",
                    volume=leg['volume']
                )
        print()
    
    def close_position(self):
        """平仓"""
        if not self.legs:
            return
            
        print(f"[平仓] 平掉蝴蝶价差: ", end="")
        for leg in self.legs:
            print(f"{leg['action']}{leg['volume']}手 {leg['type']}@{leg['strike']}", end=" ")
            
            expiry = self.get_expiry_code()
            option_symbol = f"{self.symbol}{expiry}{leg['type'][0]}{int(leg['strike']*1000):08d}"
            
            if leg['action'] == 'BUY':
                # 卖出平仓
                self.api.insert_order(
                    symbol=option_symbol,
                    direction="SELL",
                    offset="CLOSE",
                    volume=leg['volume']
                )
            else:
                # 买入平仓
                self.api.insert_order(
                    symbol=option_symbol,
                    direction="BUY",
                    offset="CLOSE",
                    volume=leg['volume']
                )
        print()
        
        self.legs = []
    
    def get_expiry_code(self):
        """获取到期日代码"""
        # 这里需要根据实际到期日格式化为TqSdk格式
        # 例如: 2405 -> C2405
        return ""
    
    def calculate_payoff(self, underlying_price):
        """
        计算到期盈亏
        
        Args:
            underlying_price: 标的价格
            
        Returns:
            float: 盈亏金额
        """
        if not self.legs:
            return 0
            
        payoff = 0
        for leg in self.legs:
            k = leg['strike']
            v = leg['volume']
            
            if leg['type'] == 'CALL':
                # 看涨期权 payoff = max(S - K, 0)
                option_payoff = max(underlying_price - k, 0)
            else:
                # 看跌期权 payoff = max(K - S, 0)
                option_payoff = max(k - underlying_price, 0)
            
            if leg['action'] == 'BUY':
                payoff += option_payoff * v
            else:
                payoff -= option_payoff * v
                
        return payoff
    
    def check_signal(self):
        """检查交易信号"""
        chain = self.get_option_chain()
        if chain is None:
            return
            
        strikes = self.select_strikes(chain)
        if strikes is None:
            print("无法选择合适的行权价")
            return
            
        k1, k2, k3 = strikes
        
        print(f"\n[{datetime.now()}]")
        print(f"  标的: {self.symbol}, 价格: {chain['underlying_price']:.4f}")
        print(f"  到期日: {chain['expiry']}")
        print(f"  行权价: K1={k1:.4f}, K2={k2:.4f}, K3={k3:.4f}")
        
        if not self.legs:
            # 构建蝴蝶价差
            legs = self.build_butterfly(k1, k2, k3)
            self.open_position(legs)
        else:
            # 检查是否需要平仓
            # 简单逻辑：距离到期日3天以内平仓
            # 实际应检查标的价格是否远离中间行权价
            
            # 暂时不平仓，等到期自动行权
            pass
    
    def run(self):
        """主循环"""
        print("=" * 60)
        print(f"期权蝴蝶价差策略启动")
        print(f"标的: {self.symbol}, 类型: {self.option_type.upper()}")
        print("=" * 60)
        
        while True:
            try:
                self.api.wait_update()
                
                # 开盘检查信号
                trading_time = self.api.get_trading_time()
                if self.api.is_changing(trading_time, "date"):
                    self.check_signal()
                    
            except KeyboardInterrupt:
                # 平仓退出
                if self.legs:
                    self.close_position()
                print("\n策略停止")
                break
            except Exception as e:
                print(f"运行错误: {e}")


def main():
    """主函数"""
    # 使用模拟账户
    api = TqApi(auth=TqAuth("YOUR_ACCOUNT", "YOUR_PASSWORD"))
    
    # 策略参数
    params = {
        'option_type': 'call',     # 'call' 或 'put'
        'days_to_expiry': 30,       # 距离到期天数
        'k_range': 0.05            # 行权价间距
    }
    
    # 启动策略 (50ETF期权)
    strategy = ButterflySpreadStrategy(api, "510050.SH", params)
    strategy.run()


if __name__ == "__main__":
    main()
