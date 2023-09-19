from dataclasses import dataclass
from datetime import datetime
import os
from typing import Literal
import pandas as pd
from logger import logger

def interval_to_minutes(interval):
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


class OHLCVDataset(pd.DataFrame):
    def __init__(self, *args, **kwargs):
        if kwargs.pop('pass_thru', False):
            return super().__init__(*args, **kwargs)
        kwargs.update({'columns': ['time', 'open', 'high', 'low', 'close', 'volume']})
        super().__init__(*args, **kwargs)
        self.set_index('time', inplace=True)
        self._validate()

    def _validate(self):
        pass
    
    def _standardize_freq(self, freq):
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
    
    def change(self, freq):
        freq = self._standardize_freq(freq)
        return self.resample(freq).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        })

    @classmethod
    def from_csv(cls, filename):
        if not os.path.exists(filename):
            logger.fatal(f'File {filename} does not exist')
            raise FileNotFoundError(f'File {filename} does not exist')
        ds = pd.read_csv(filename)
        ds.columns = ['time', 'open', 'high', 'low', 'close', 'volume']
        ds['time'] = pd.to_datetime(ds['time'], unit='s')
        ds.set_index('time', inplace=True)
        ds['open'] = ds['open'].astype(float)
        ds['high'] = ds['high'].astype(float)
        ds['low'] = ds['low'].astype(float)
        ds['close'] = ds['close'].astype(float)
        ds['volume'] = ds['volume'].astype(float)
        return cls(ds, pass_thru=True)
    
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


@dataclass
class Order:
    def __init__(self, oid, symbol, market, side, price, created, deal_funds, deal_size, funds, **kwargs) -> None:
        self.oid: str = oid
        self.symbol: ExchangeSymbol = symbol
        self.market: str = market
        self.side: str = side
        self.price: float = price
        
        self.fee: float = kwargs.get('fee', 0)
        self.created: datetime = created
        
        self.deal_funds: float = deal_funds
        self.deal_size: float = deal_size
        self.funds: float = funds
        
        self.client_oid: str = kwargs.get('client_oid')
        self.type: Literal['LIMIT', 'MARKET'] = kwargs.get('type', 'MARKET')
        self.status: Literal['ACTIVE', 'FILLED', 'CANCELLED'] = kwargs.get('status', 'ACTIVE')

    def json(self):
        return {
            'oid': self.oid,
            'symbol': self.symbol.json(),
            'market': self.market,
            'side': self.side,
            'price': self.price,
            'type': self.type,
            'fee': self.fee,
            'created': self.created,
            'status': self.status,
            'deal_funds': self.deal_funds,
            'deal_size': self.deal_size,
            'funds': self.funds,
            'client_oid': self.client_oid,
        }


class ExchangeSymbol:
    def __init__(self, name, base, quote, **kwargs) -> None:
        self.name = name
        self.base = base
        self.quote = quote
        self.base_precision = kwargs.get('base_precision')
        self.quote_precision = kwargs.get('quote_precision')
        self.spot_trading_enabled = kwargs.get('spot_trading_enabled', True)
        self.margin_trading_enabled = kwargs.get('margin_trading_enabled', False)
        self.filters = kwargs.get('filters', [])
    
    def json(self):
        return {
            'name': self.name,
            'base': self.base,
            'quote': self.quote,
            'base_precision': self.base_precision,
            'quote_precision': self.quote_precision,
            'spot_trading_enabled': self.spot_trading_enabled,
            'margin_trading_enabled': self.margin_trading_enabled,
        }