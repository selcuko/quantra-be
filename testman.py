from dataclasses import dataclass
from datetime import datetime
import json
import os
from typing import Literal
from logger import logger
from numpy import NaN
import pandas as pd

@dataclass
class Trade:
    price: float
    quantity: float
    datetime: datetime
    position: Literal["buy", "sell"]

    def to_dict(self):
        return {
            'price': self.price,
            'quantity': self.quantity,
            'datetime': str(self.datetime),
            'position': self.position,
        }


class TestManager:
    def __init__(self, *args, **kwargs):
        """Manager class to hold testing data, analyze results, and keep track of trades."""
        self.trades = []
        self.capital = kwargs.get('capital', 1000)
        self.assets = 0
        self.commission = kwargs.get('commission', 0.002)
        self.shutdown_percent = kwargs.get('shutdown_percent', 50)
        self.wins = 0
        self.losses = 0
        self.bought = False
        self.bought_price = 0
        self.profit_from_last_trade = 0
        self.sold_price = 0
        self.sold_at_shutdown = False
        self.buy_signals = 0
        self.sell_signals = 0
        self.verbose = kwargs.get('verbose', False)
        self.symbol = kwargs.get('symbol', None)
        self.market = kwargs.get('market', None)
        self.last_kline_dt = None
        self.live = kwargs.get('live', False)
        self.strategy = kwargs.get('strategy', None)
        self.strategy_name = self.strategy.name if self.strategy else None
        self.strategy_params = self.strategy.params if self.strategy else None


    def buy(self, kline):
        self.buy_signals += 1
        if self.bought:
            if self.verbose:
                print('Already bought, cannot buy again - ignoring buy signal')
            return
        price = kline['close']
        self.bought = True
        self.bought_price = price
        self.assets = (1 - self.commission) * (self.capital / price)
        self.capital = 0
        trade = Trade(price, self.assets, kline['time'], 'buy')
        self.trades.append(trade)
        self.last_kline_dt = kline['time']

    def sell(self, kline):
        self.sell_signals += 1
        if not self.bought:
            if self.verbose:
                print('Not bought, cannot sell - ignoring sell signal')
            return
        price = kline['close']
        self.bought = False
        self.capital = (1 - self.commission) * (self.assets * price)
        self.assets = 0
        self.profit_from_last_trade = (price - self.bought_price) / self.bought_price * 100
        self.sold_price = price
        if price > self.bought_price:
            self.wins += 1
        else:
            self.losses += 1
        trade = Trade(price, self.capital, kline['time'], 'sell')
        self.trades.append(trade)
        self.last_kline_dt = kline['time']
    
    def shutdown(self):
        self.save_to_disk()
    
    @property
    def equity(self):
        """Total equity in USD."""
        return self.capital + self.assets * self.bought_price

    @property
    def profit(self):
        """Profit in percent."""
        return ((self.equity - 1000) / 1000) * 100
    
    @property
    def win_rate(self):
        """Win rate in percent."""
        if self.wins == 0 and self.losses == 0:
            return NaN
        return self.wins / (self.wins + self.losses) * 100

    def summary(self):
        if self.live:
            txt = f'[{datetime.now().strftime("%d-%m-%Y %H:%M:%S")}] Position: {"IN" if self.bought else "OUT"} | Trades: {len(self.trades)} | Profit: {self.profit:.2f}% | Win Rate: {self.win_rate:.2f}% | Last Trade: {self.profit_from_last_trade:.2f}% | Capital: {self.capital:.2f} | Assets: {self.assets:.2f}'    
        else:
            if self.last_kline_dt:
                txt = f'[{self.last_kline_dt.strftime("%d-%m-%Y %H:%M:%S")}] Position: {"IN" if self.bought else "OUT"} | Trades: {len(self.trades)} | Profit: {self.profit:.2f}% | Win Rate: {self.win_rate:.2f}% | Last Trade: {self.profit_from_last_trade:.2f}% | Capital: {self.capital:.2f} | Assets: {self.assets:.2f}'    
            else:
                txt = f'[%dd-%mm-%YYYY %HH:%MM:%SS] Position: {"IN" if self.bought else "OUT"} | Trades: {len(self.trades)} | Profit: {self.profit:.2f}% | Win Rate: {self.win_rate:.2f}% | Last Trade: {self.profit_from_last_trade:.2f}% | Capital: {self.capital:.2f} | Assets: {self.assets:.2f}'
        if self.symbol and self.market:
            txt = f'[{self.market.upper()}:{self.symbol.upper()}]' + txt
        return txt
    
    def to_dict(self):
        return {
            'trades_count': len(self.trades),
            'capital': self.capital,
            'assets': self.assets,
            'commission': self.commission,
            'shutdown_percent': self.shutdown_percent,
            'wins': self.wins,
            'losses': self.losses,
            'bought': self.bought,
            'bought_price': self.bought_price,
            'profit_from_last_trade': self.profit_from_last_trade,
            'sold_price': self.sold_price,
            'sold_at_shutdown': self.sold_at_shutdown,
            'buy_signals': self.buy_signals,
            'sell_signals': self.sell_signals,
            'symbol': self.symbol,
            'market': self.market,
            'strategy_name': self.strategy_name,
            'strategy_params': self.strategy_params,
            'trades': [trade.to_dict() for trade in self.trades],
        }

    def save_to_disk(self, filedir=None):
        if not filedir:
            if self.symbol and self.market and self.strategy:
                filedir = f'testman/testman-{datetime.now()}-{self.symbol.upper()}-{self.market.upper()}-{self.strategy_name}.json'
            else:
                filedir = f'testman/testman-{datetime.now()}.json'
        os.makedirs(os.path.dirname(filedir), exist_ok=True)
        if os.path.exists(filedir):
            logger.error(f'File {filedir} already exists, failed to save')
            return
        with open(filedir, 'w') as f:
            f.write(json.dumps(self.to_dict()))
        logger.info(f'Saved TestMan instance to {filedir}')
        return filedir

    