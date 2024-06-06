from datetime import datetime
from decimal import Decimal
import math
import os
from typing import Literal

import pandas as pd

from logger import logger


def interval_to_minutes(interval:str) -> int:
    try:
        return {
            '1 min': 1,
            '3 min': 3,
            '5 min': 5,
            '15 min': 15,
            '30 min': 30,
            '1 hour': 60,
            '2 hour': 120,
            '4 hour': 240,
            '6 hour': 360,
            '8 hour': 480,
            '12 hour': 720,
            '1 day': 1440,
            '3 day': 4320,
            '1 week': 10080,
            '1 month': 43200,
        }[interval]
    except KeyError:
        raise ValueError(f'Intverval "{interval}" is in invalid format, provide in the form of "1 min" or "1 hour"')


class OHLCVDataset(pd.DataFrame):
    def __init__(self, *args, **kwargs):
        if kwargs.pop('pass_thru', False):
            super().__init__(*args, **kwargs)
            return
        kwargs.update({'columns': ['time', 'open', 'high', 'low', 'close', 'volume']})
        super().__init__(*args, **kwargs)
        self.set_index('time', inplace=True)

    def __new__(cls, *args, **kwargs):
        return super().__new__(cls)

    @staticmethod
    def _standardize_freq(freq):
        return {
            '1 min': '1T',
            '3 min': '3T',
            '5 min': '5T',
            '15 min': '15T',
            '30 min': '30T',
            '1 hour': '1H',
            '2 hour': '2H',
            '4 hour': '4H',
            '6 hour': '6H',
            '8 hour': '8H',
            '12 hour': '12H',
            '1 day': '1D',
            '3 day': '3D',
            '1 week': '1W',
            '1 month': '1M',
        }[freq]

    def change(self, freq) -> "OHLCVDataset":
        freq = self._standardize_freq(freq)
        new_ds = self.resample(freq).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        })
        return OHLCVDataset(new_ds, pass_thru=True)

    @classmethod
    def from_csv_as_standard_candles(cls, filename):
        ds = pd.read_csv(filename)
        ds.columns = ['time', 'open', 'high', 'low', 'close', 'volume']
        ds['time'] = pd.to_datetime(ds['time'], unit='s')
        ds.set_index('time', inplace=True)
        ds['open'] = ds['open'].astype(float)
        ds['high'] = ds['high'].astype(float)
        ds['low'] = ds['low'].astype(float)
        ds['close'] = ds['close'].astype(float)
        ds['volume'] = ds['volume'].astype(float)
        return OHLCVDataset(ds, pass_thru=True)

    def convert_to_heikin_ashi(self):
        ds = self.copy()
        ds['open'] = (ds['open'].shift(1) + ds['close'].shift(1)) / 2
        ds['open'].iloc[0] = ds['open'].iloc[1]
        ds['high']   = ds[['open', 'close', 'high']].max(axis=1)
        ds['low']    = ds[['open', 'close', 'low']].min(axis=1)
        ds['close']  = (ds['open'] + ds['high'] + ds['low'] + ds['close']) / 4
        ds['volume'] = ds['volume']
        return OHLCVDataset(ds, pass_thru=True)

    @classmethod
    def from_csv_as_heikin_ashi_candles(cls, filename):
        ds = pd.read_csv(filename)
        ds.columns = ['time', 'open', 'high', 'low', 'close', 'volume']
        ds['time'] = pd.to_datetime(ds['time'], unit='s')
        ds.set_index('time', inplace=True)
        ds['open'] = ds['open'].astype(float)
        ds['high'] = ds['high'].astype(float)
        ds['low'] = ds['low'].astype(float)
        ds['close'] = ds['close'].astype(float)
        ds['volume'] = ds['volume'].astype(float)
        ha_ds = pd.DataFrame(index=ds.index, columns=['open', 'high', 'low', 'close', 'volume'])

        ha_ds['open'] = (ds['open'].shift(1) + ds['close'].shift(1)) / 2
        ha_ds['open'].iloc[0] = ds['open'].iloc[0]  # For the first row
        ha_ds['high']   = ds[['open', 'close', 'high']].max(axis=1)
        ha_ds['low']    = ds[['open', 'close', 'low']].min(axis=1)
        ha_ds['close']  = (ds['open'] + ds['high'] + ds['low'] + ds['close']) / 4
        ha_ds['volume'] = ds['volume']
        return OHLCVDataset(ha_ds, pass_thru=True)

    @classmethod
    def from_csv(cls, filename, candle_type:Literal['standard', 'heikin_ashi'] = 'standard'):
        if not os.path.exists(filename):
            logger.fatal(f'File {filename} does not exist')
            raise FileNotFoundError(f'File {filename} does not exist')
        if candle_type == 'standard':
            return cls.from_csv_as_standard_candles(filename)
        elif candle_type == 'heikin_ashi':
            return cls.from_csv_as_heikin_ashi_candles(filename)
        else:
            raise ValueError(f'Invalid candle_type "{candle_type}", must be either "standard" or "heikin_ashi"')

    # modify [] operator to return a OHLCVDataset
    def __getitem__(self, key):
        k = super().__getitem__(key)
        if isinstance(k, pd.DataFrame):
            return OHLCVDataset(k, pass_thru=True)
        return k
    
    def add_dataset(self, ds):
        return OHLCVDataset(pd.concat([self, ds]), pass_thru=True)

    def copy(self, *args, **kwargs) -> "OHLCVDataset":
        return OHLCVDataset(super().copy(*args, **kwargs), pass_thru=True)


class SymbolMetrics:
    def __init__(self, market_data) -> None:
        self.price = market_data['current_price']['usd']
        self.atl = {
            'price': market_data['atl']['usd'],
            'percentage': market_data['atl_change_percentage'],
            'date': market_data['atl_date'],
        }
        self.ath = {
            'price': market_data['ath']['usd'],
            'percentage': market_data['ath_change_percentage'],
            'date': market_data['ath_date'],
        }
        self.volume = market_data['total_volume']['usd']
        self.day = {
            'high': market_data['high_24h']['usd'],
            'low': market_data['low_24h']['usd'],
            'change': market_data['price_change_24h'],
            'change_percentage': market_data['price_change_percentage_24h'],
        }
        self.total_supply = market_data['total_supply']
        self.circulating_supply = market_data['circulating_supply']
        self.supply_ratio = (self.circulating_supply / self.total_supply) * 100 if self.total_supply else None
        self.max_supply = market_data['max_supply']
        self.market_cap = market_data['market_cap']['usd']
        self.max_conv = (self.price - self.atl['price']) / (self.ath['price'] - self.atl['price']) if self.ath['price'] != self.atl['price'] else None
        self.min_conv = (self.ath['price'] - self.price) / (self.ath['price'] - self.atl['price']) if self.ath['price'] != self.atl['price'] else None

        self.updated = datetime.fromisoformat(market_data['last_updated'])



class Bid:
    def __init__(self, price:float|int|Decimal, size:float|int|Decimal, delta:int|float|Decimal=0, count=1) -> None:
        self.price = Decimal(price)
        self.size = Decimal(size)
        self.delta = delta
        self.count = count
        self.value = self.price * self.size
    
    def __str__(self):
        return f'{self.price}\t${self.value:.2f} (^{self.delta:.2f})'
    
    def json(self):
        return {
            'price': str(self.price),
            'size': str(self.size),
            'delta': str(self.delta),
            'count': self.count,
            'value': str(self.value),
        }

class OrderBook:
    def __init__(self):
        self.bids:dict[Decimal, Bid] = {}
        self.asks:dict[Decimal, Bid] = {}

    def get_bid(self, price:float|int|Decimal) -> Bid:
        return self.bids.get(Decimal(price), Bid(price, 0))

    def get_ask(self, price:float|int|Decimal) -> Bid:
        return self.asks.get(Decimal(price), Bid(price, 0))

    def sort(self):
        self.bids = dict(sorted(self.bids.items(), key=lambda x: x[0], reverse=True))
        self.asks = dict(sorted(self.asks.items(), key=lambda x: x[0]))

    def group(self, precision:int):
        def _round(number: Decimal, precision=precision):
            if precision >= 0:
                precision -= 1
                return math.floor(number / 10**precision) * 10**precision
            else:
                return round(number, -precision)
        new_ob = OrderBook()
        old_ob = self.copy()
        for bid in old_ob.bids.values():
            price = _round(bid.price)
            new_bid = new_ob.bids.get(price, Bid(price, 0))
            new_bid.size += bid.size
            new_bid.count += 1
            new_bid.value += bid.value
            new_ob.bids[price] = new_bid
        for ask in old_ob.asks.values():
            price = _round(ask.price)
            new_ask = new_ob.asks.get(price, Bid(price, 0))
            new_ask.size += ask.size
            new_ask.count += 1
            new_ask.value += ask.value
            new_ob.asks[price] = new_ask
        return new_ob

    def copy(self):
        new_ob = OrderBook()
        new_ob.bids = self.bids.copy()
        new_ob.asks = self.asks.copy()
        return new_ob

    def get_best(self, limit=5):
        self.sort()
        best_bids = sorted(self.bids.values(), key=lambda x: x.price, reverse=True)[:limit]
        best_asks = sorted(self.asks.values(), key=lambda x: x.price)[:limit]
        return best_bids, best_asks

    def json(self):
        ob = self.copy()
        ob.sort()
        return {
            'bids': [bid.json() for bid in ob.bids.values()],
            'asks': [ask.json() for ask in ob.asks.values()],
        }

    def format(self, limit=5):
        '''Format the orderbook to a string'''
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.sort()
        bids = '\n'.join([str(bid) for bid in list(self.bids.values())[:limit]])
        asks = '\n'.join([str(ask) for ask in list(self.asks.values())[:limit]])
        return f'''
-------------------------
{now}
Best {limit} Bids:
{bids}

Best {limit} Asks:
{asks}

-------------------------'''

    def overview(self):
        '''Return a brief overview of the orderbook'''
        return {
            'bids': sum([bid.value for bid in self.bids.values()]),
            'asks': sum([ask.value for ask in self.asks.values()]),
            'bid_count': len(self.bids),
            'ask_count': len(self.asks),
        }
