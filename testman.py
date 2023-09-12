from dataclasses import dataclass
from datetime import datetime
import json
import os
from typing import Literal
from logger import logger
from numpy import NaN
import pandas as pd

@dataclass
class Performance:
    sharpe_ratio: float = None
    sortino_ratio: float = None
    calmar_ratio: float = None
    omega_ratio: float = None
    tail_ratio: float = None
    common_sense_ratio: float = None
    sterling_ratio: float = None
    burke_ratio: float = None
    information_ratio: float = None
    kappa_three_ratio: float = None
    gain_loss_ratio: float = None
    upside_potential_ratio: float = None
    downside_potential_ratio: float = None
    profitability: float = None
    max_drawdown: float = None
    avg_drawdown: float = None
    min_drawdown: float = None
    max_holdtime: datetime = None
    avg_holdtime: datetime = None
    min_holdtime: datetime = None
    max_runup: float = None
    avg_runup: float = None
    min_runup: float = None
    total_profit: float = None
    gross_profit: float = None
    gross_loss: float = None
    profit_factor: float = None
    cumulative_return: float = None
    avg_annual_return: float = None
    avg_monthly_return: float = None
    avg_weekly_return: float = None
    avg_daily_return: float = None
    avg_hourly_return: float = None
    annual_volatility: float = None
    skewness: float = None
    kurtosis: float = None
    value_at_risk: float = None
    daily_value_at_risk: float = None
    total_turnover: float = None
    avg_turnover: float = None
    avg_daily_turnover: float = None
    avg_monthly_turnover: float = None
    avg_annual_turnvover: float = None
    stability: float = None
    alpha: float = None
    beta: float = None
    eaten_by_commissions: float = None
    _risk_free_rate = 0.15 # as of 2023, in Turkey


    def to_dict(self):
        attrs = [attr for attr in dir(self) if not callable(getattr(self, attr)) and not attr.startswith("__") and not getattr(self, attr) is None]
        return {attr: getattr(self, attr) for attr in attrs}
    
    @classmethod
    def calculate(cls, trades, capital):
        drawdown_trades_count = len([trade.profit_pct for trade in trades if isinstance(trade.profit_pct, float) and trade.profit_pct < 0])
        runup_trades_count = len([trade.profit_pct for trade in trades if isinstance(trade.profit_pct, float) and trade.profit_pct > 0])
        return cls(
            max_drawdown = f'{min([trade.profit_pct for trade in trades if isinstance(trade.profit_pct, float) and trade.profit_pct < 0]):.2f}%',
            avg_drawdown = f'{sum([trade.profit_pct for trade in trades if isinstance(trade.profit_pct, float) and trade.profit_pct < 0]) / (drawdown_trades_count):.2f}%',
            min_drawdown = f'{max([trade.profit_pct for trade in trades if isinstance(trade.profit_pct, float) and trade.profit_pct < 0]):.2f}%',
            min_runup = f'{min([trade.profit_pct for trade in trades if isinstance(trade.profit_pct, float) and trade.profit_pct > 0]):.2f}%',
            avg_runup = f'{sum([trade.profit_pct for trade in trades if isinstance(trade.profit_pct, float) and trade.profit_pct > 0]) / (runup_trades_count):.2f}%',
            max_runup = f'{max([trade.profit_pct for trade in trades if isinstance(trade.profit_pct, float) and trade.profit_pct > 0]):.2f}%',
            total_profit = trades[-1].equity - capital,
            gross_profit = sum([trade.profit_pct for trade in trades if isinstance(trade.profit_pct, float) and trade.profit_pct > 0]),
            gross_loss = sum([trade.profit_pct for trade in trades if isinstance(trade.profit_pct, float) and trade.profit_pct < 0]),
            total_turnover = sum([trade.capital for trade in trades]),
            skewness = pd.Series([trade.profit_pct for trade in trades]).skew(),
            kurtosis = pd.Series([trade.profit_pct for trade in trades]).kurtosis(),
            profit_factor = abs(sum([trade.profit_pct for trade in trades if isinstance(trade.profit_pct, float) and trade.profit_pct > 0]) / sum([trade.profit_pct for trade in trades if isinstance(trade.profit_pct, float) and trade.profit_pct < 0])),
            cumulative_return = ((trades[-1].equity - capital) / capital) * 100,
            profitability = len([trade.profit_pct for trade in trades if isinstance(trade.profit_pct, float) and trade.profit_pct > 0]) / len([trade.profit_pct for trade in trades if isinstance(trade.profit_pct, float)]) * 100,
            burke_ratio = (trades[-1].equity - capital) / abs(min([trade.profit_pct for trade in trades if isinstance(trade.profit_pct, float) and trade.profit_pct < 0])),
            sterling_ratio = (trades[-1].equity - capital) / abs(max([trade.profit_pct for trade in trades if isinstance(trade.profit_pct, float) and trade.profit_pct < 0])),
            beta = pd.Series([trade.profit_pct for trade in trades]).cov(pd.Series([trade.profit_pct for trade in trades])),
            alpha = ((trades[-1].equity - capital) / capital) - cls._risk_free_rate,
            common_sense_ratio = (trades[-1].equity - capital) / abs(min([trade.profit_pct for trade in trades if isinstance(trade.profit_pct, float) and trade.profit_pct < 0])),
            downside_potential_ratio = abs(sum([trade.profit_pct for trade in trades if isinstance(trade.profit_pct, float) and trade.profit_pct < 0]) / len([trade.profit_pct for trade in trades if isinstance(trade.profit_pct, float) and trade.profit_pct < 0])),
            upside_potential_ratio = sum([trade.profit_pct for trade in trades if isinstance(trade.profit_pct, float) and trade.profit_pct > 0]) / len([trade.profit_pct for trade in trades if isinstance(trade.profit_pct, float) and trade.profit_pct > 0]),
            eaten_by_commissions = sum([trade.equity * 0.002 for trade in trades]),
        )



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
    hold_time: datetime

    def to_dict(self):
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
        }


class TestManager:
    def __init__(self, *args, **kwargs):
        """Manager class to hold testing data, analyze results, and keep track of trades."""
        self.trades = []
        self.initial_capital = self.capital = kwargs.get('capital', 1000)
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
        trade = Trade(
            number=len(self.trades) + 1,
            price=price,
            assets=self.assets,
            capital=self.capital,
            datetime=kline['time'],
            position='buy',
            equity=self.equity,
            profit=None,
            profit_pct=None,
            hold_time=None,
        )
        self.trades.append(trade)
        self.last_kline_dt = kline['time']

    def sell(self, kline):
        self.sell_signals += 1
        if not self.bought:
            if self.verbose:
                print('Not bought, cannot sell - ignoring sell signal')
            return
        price = kline['close']
        old_equity = self.equity
        self.bought = False
        self.capital = (1 - self.commission) * (self.assets * price)
        self.assets = 0
        self.profit_from_last_trade = self.equity - old_equity
        self.sold_price = price
        if price > self.bought_price:
            self.wins += 1
        else:
            self.losses += 1
        trade = Trade(
            number=len(self.trades) + 1,
            price=price,
            assets=self.assets,
            capital=self.capital,
            datetime=kline['time'],
            position='sell',
            equity=self.equity,
            profit=self.profit_from_last_trade,
            profit_pct=(self.profit_from_last_trade / self.bought_price) * 100,
            hold_time=None,
        )
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
            'performance': Performance.calculate(self.trades, self.initial_capital).to_dict(),
            'trades': [trade.to_dict() for trade in self.trades],
        }

    def save_to_disk(self, filedir=None):
        if not filedir:
            if self.symbol and self.market and self.strategy:
                filedir = f'testman/testman-{datetime.now()}-{self.symbol.upper()}-{self.market.upper()}-{self.strategy_name}.json'
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

    