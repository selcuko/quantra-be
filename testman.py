from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import os
from typing import Literal

import pytz
from logger import logger
from markets import Market
from models import Order

class Performance:
    def __init__(self, trades:list["Trade"], initial_capital:float=1000.):
        self.trades = [trade for trade in trades if trade.position == 'sell']
        self.initial_capital = initial_capital
        self.winning_trades = [trade for trade in self.trades if trade.profit > 0]
        self.losing_trades = [trade for trade in self.trades if trade.profit < 0]
        self.total_trades = len(self.trades)
        self.total_wins = len(self.winning_trades)
        self.total_losses = len(self.losing_trades)
        self.get_profit_related()
        self.get_ratios()
        self.get_analytics()

    def get(self, key):
        try:
            value = getattr(self, key)
            if isinstance(value, float):
                value = round(value, 2)
            return value
        except AttributeError:
            return None

    def to_dict(self):
        return {
            'total_trades': self.get('total_trades'),
            'total_wins': self.get('total_wins'),
            'total_losses': self.get('total_losses'),
            'gross_loss': self.get('gross_loss'),
            'total_profit': self.get('total_profit'),
            'gross_profit': self.get('gross_profit'),
            'net_profit': self.get('net_profit'),
            'total_hold_time': str(self.get('total_hold_time')),
            'total_turnover': self.get('total_turnover'),
            'average_hold_time': str(self.get('average_hold_time')),
            'average_turnover': self.get('average_turnover'),
            'average_profit': self.get('average_profit'),
            'average_profit_pct': self.get('average_profit_pct'),
            'win_rate': self.get('win_rate'),
            'win_loss_ratio': self.get('win_loss_ratio'),
            'profit_factor': self.get('profit_factor'),
            'avg_profit': self.get('avg_profit'),
            'avg_profit_pct': self.get('avg_profit_pct'),
            'min_profit': self.get('min_profit'),
            'min_profit_pct': self.get('min_profit_pct'),
            'max_profit': self.get('max_profit'),
            'max_profit_pct': self.get('max_profit_pct'),
            'avg_loss': self.get('avg_loss'),
            'avg_loss_pct': self.get('avg_loss_pct'),
            'min_loss': self.get('min_loss'),
            'min_loss_pct': self.get('min_loss_pct'),
            'max_loss': self.get('max_loss'),
            'max_loss_pct': self.get('max_loss_pct'),
        }

    def get_profit_related(self):
        if not self.total_trades:
            return
        self.total_profit = sum([trade.profit for trade in self.trades])
        self.total_hold_time = sum([trade.hold_time for trade in self.trades], timedelta())
        self.total_turnover = sum([trade.equity for trade in self.trades])
        self.gross_profit = sum([trade.profit for trade in self.winning_trades])
        self.gross_loss = sum([trade.profit for trade in self.losing_trades])
        self.net_profit = self.gross_profit + self.gross_loss
        
        self.average_hold_time = self.total_hold_time / self.total_trades
        self.average_turnover = self.total_turnover / self.total_trades
        self.average_profit = self.total_profit / self.total_trades
        self.average_profit_pct = sum([trade.profit_pct for trade in self.trades]) / self.total_trades
    
    def get_ratios(self):
        if not self.total_trades:
            return
        self.win_rate = self.total_wins / self.total_trades
        if self.total_losses:
            self.win_loss_ratio = self.total_wins / self.total_losses
            self.profit_factor = self.total_profit / self.total_losses
        
    def get_analytics(self):
        if not self.total_trades:
            return
        if self.winning_trades and self.total_wins:
            self.avg_profit = sum([trade.profit for trade in self.winning_trades]) / self.total_wins
            self.avg_profit_pct = sum([trade.profit_pct for trade in self.winning_trades]) / self.total_wins
        if self.winning_trades:
            self.min_profit = min([trade.profit for trade in self.winning_trades])
            self.min_profit_pct = min([trade.profit_pct for trade in self.winning_trades])
            self.max_profit = max([trade.profit for trade in self.winning_trades])
            self.max_profit_pct = max([trade.profit_pct for trade in self.winning_trades])
        if self.losing_trades and self.total_losses:
            self.avg_loss = sum([trade.profit for trade in self.losing_trades]) / self.total_losses
            self.avg_loss_pct = sum([trade.profit_pct for trade in self.losing_trades]) / self.total_losses
        if self.losing_trades:
            self.min_loss = min([trade.profit for trade in self.losing_trades])
            self.min_loss_pct = min([trade.profit_pct for trade in self.losing_trades])
            self.max_loss = max([trade.profit for trade in self.losing_trades])
            self.max_loss_pct = max([trade.profit_pct for trade in self.losing_trades])    

@dataclass
class Trade:
    number: int
    price: float
    assets: float
    capital: float
    datetime: datetime
    position: Literal["buy", "sell"]
    equity: float
    profit: float
    profit_pct: float
    hold_time: timedelta
    rawrow: dict

    def to_dict(self):
        self.rawrow.pop('time', None)
        return {
            'number': self.number,
            'price': self.price,
            'datetime': str(self.datetime),
            'position': self.position,
            'equity': self.equity,
            'profit': self.profit,
            'profit_pct': self.profit_pct,
            'hold_time': str(self.hold_time),
            'assets': self.assets,
            'capital': self.capital,
            'rawrow': self.rawrow,
        }


class TestManager:
    def __init__(self, 
                 symbol:str, 
                 market:Market, 
                 type:Literal['live.basic', 'live.sandbox', 'live.mainnet', 'backtest'],
                 strategy:callable,
                 capital:float,
                 interval:str,
                 commission:dict={},
                 start:datetime=None,
                 end:datetime=None,
                 verbose:bool=False,):
        """Manager class to hold testing data, analyze results, and keep track of trades."""
        self.symbol = symbol
        self.market = market
        self.start = start
        self.end = end
        self.interval = interval
        self.initial_capital = capital
        self.type = type
        self.strategy = strategy

        self.trades = []
        self.assets = 0
        self.commissions = commission
        if isinstance(self.commissions, float):
            self.commissions = {'buyer': self.commission, 'seller': self.commission}
        self.buyer_commission = self.commissions.get('buyer', 0)
        self.seller_commission = self.commissions.get('seller', 0)
        self.wins = 0
        self.losses = 0
        self.bought = False
        self.bought_price = 0
        self.sold_price = 0
        self.last_profit_pct = 0
        self.buy_signals = 0
        self.sell_signals = 0
        self.verbose = verbose
        self.last_kline_dt = None     
        self.capital = capital   
        self.last_kline = None

    def buy(self, kline, sync:Order=None):
        self.buy_signals += 1
        if self.bought:
            return
        self.update(kline)
        price = self.last_kline['close']
        self.bought = True
        self.bought_price = price
        if sync:
            self.assets += sync.deal_size
            self.capital -= sync.deal_funds
            if self.capital < 0:
                logger.error('Capital is less than 0, TestMan went out of sync with market data. (setting to 0)')
                self.capital = 0
        else:
            if self.type in ['live.sandbox', 'live.mainnet']:
                logger.error('Sync order is not provided in live mode, results may be inaccurate.')
            self.assets = (1 - self.buyer_commission) * (self.capital / price)
            self.capital = 0
        trade = Trade(
            number=len(self.trades) // 2 + 1,
            price=price,
            assets=self.assets,
            capital=self.capital,
            datetime=kline['time'],
            position='buy',
            equity=self.equity,
            profit=None,
            profit_pct=None,
            hold_time=None,
            rawrow=kline
        )
        self.trades.append(trade)
        return True

    def sell(self, kline, sync:Order=None):
        self.sell_signals += 1
        if not self.bought:
            return
        self.update(kline)
        price = self.last_kline['close']
        self.bought = False
        if sync:
            self.capital += sync.deal_funds
            self.assets -= sync.deal_size
            if self.assets < 0:
                logger.error('Assets is less than 0, TestMan went out of sync with market data. (setting to 0)')
                self.assets = 0
        else:
            if self.type in ['live.sandbox', 'live.mainnet']:
                logger.error('Sync order is not provided in live mode, results may be inaccurate.')
            self.capital = (1 - self.seller_commission) * (self.assets * price)
            self.assets = 0
        self.last_profit = self.equity - self.trades[-1].equity
        self.last_profit_pct = self.last_profit * 100 / self.trades[-1].equity
        self.sold_price = price
        if price > self.bought_price:
            self.wins += 1
        else:
            self.losses += 1
        trade = Trade(
            number=len(self.trades) // 2 + 1,
            price=price,
            assets=self.assets,
            capital=self.capital,
            datetime=kline['time'],
            position='sell',
            equity=self.equity,
            profit=self.last_profit,
            profit_pct=self.last_profit_pct,
            hold_time=kline['time'] - self.trades[-1].datetime,
            rawrow=kline
        )
        self.trades.append(trade)
        return True
    
    def shutdown(self):
        self.save_to_disk()
    
    @property
    def equity(self):
        """Total equity in USD."""
        return self.capital + self.assets * self.last_kline['close']

    @property
    def profit(self):
        """Profit in percent."""
        return ((self.equity - self.initial_capital) / self.initial_capital) * 100

    def summary(self):
        dtime = f'%dd-%mm-%YYYY %HH:%MM:%SS'
        if self.type.startswith('live'):
            dtime = datetime.now(tz=pytz.UTC).strftime("%d-%m-%Y %H:%M:%S")
        elif self.last_kline_dt:
            dtime = self.last_kline_dt.strftime("%d-%m-%Y %H:%M:%S")
        number = self.trades[-1].number if self.trades else 0
        txt = f'''\
[{dtime}][{number:>3d}:{" IN" if self.bought else "OUT"}] \
Equity: {self.equity:>3.2f} USDT | \
Price: {self.last_kline["close"]:>3.4f} USDT | \
Profit: {self.profit:>4.2f}% | \
Last trade: {self.last_profit_pct:>3.2f}% | \
Assets: {self.assets:>3.2f} | \
Capital: {self.capital:>3.2f} USDT '''
        return txt
    
    def to_dict(self):
        return {
            'profit_pct': round(self.profit, 2),
            'start': str(self.start),
            'end': str(self.end),
            'duration': str((self.end - self.start) if self.end and self.start else None),
            'interval': self.interval,
            'type': self.type,
            'trades_count': len(self.trades) // 2,
            'capital': self.capital,
            'assets': self.assets,
            'commission': self.commissions,
            'wins': self.wins,
            'losses': self.losses,
            'bought': self.bought,
            'buy_signals': self.buy_signals,
            'sell_signals': self.sell_signals,
            'symbol': self.symbol,
            'market': self.market.json(),
            'strategy': self.strategy.json(),
            'performance': Performance(self.trades, self.initial_capital).to_dict(),
            'trades': [trade.to_dict() for trade in self.trades],
        }

    def save_to_disk(self, filedir=None):
        if not filedir:
            if self.symbol and self.market and self.strategy:
                filedir = f'testman/testman-{datetime.now()}-{self.symbol.upper()}-{self.market.name.upper()}-{self.strategy.name}.json'
            else:
                filedir = f'testman/testman-{datetime.now()}.json'
        filedir = filedir.replace(' ', '_').replace(':', '-')
        os.makedirs(os.path.dirname(filedir), exist_ok=True)
        if os.path.exists(filedir):
            logger.error(f'File {filedir} already exists, failed to save')
            return
        with open(filedir, 'w') as f:
            f.write(json.dumps(self.to_dict(), indent=4))
        logger.info(f'Saved TestMan instance to {filedir}')
        return filedir

    def update(self, kline):
        self.last_kline = kline
        self.last_kline_dt = kline['time']
