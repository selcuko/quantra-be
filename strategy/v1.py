import pandas as pd
import pandas_ta  # required to use pandas_ta indicators

from models import OHLCVDataset
from strategy.interface import Strategy


def merge_dicts(d1, d2):
    # deep merge two dicts into a new one
    d = d1.copy()
    for k, v in d2.items():
        if k in d and isinstance(d[k], dict):
            d[k] = merge_dicts(d[k], v)
        else:
            d[k] = v
    return d


class StrategyV1(Strategy):
    def __init__(self, params={}):
        self.params = merge_dicts(self.default_params(), params)
        self.name = 'StrategyV1.Lisa.PandasTA'
        self.ds = OHLCVDataset(pd.DataFrame())
    
    def __call__(self, ds:OHLCVDataset):
        return self.calculate(ds)

    def default_params(self):
        return {
            'macd': {
                'fast': 12,
                'slow': 26,
                'signal': 9
            },
            'stochrsi': {
                'length': 3,
                'rsi_length': 14,
                'k': 3,
                'd': 3
            },
            't3': {
                'length': 7,
                'a': 0.7
            },
            'volume': {
                'ma': 20
            },
            'source': 'close',
        }

    def get_source(self, src = 'close'):
        if src == 'volume_ma':
            self.ds['volume_ma'] = self.ds['volume'].rolling(window=self.params['volume']['ma']).mean()
        elif src == 'ohlc4':
            self.ds['ohlc4'] = (self.ds['high'] + self.ds['low'] + self.ds['open'] + self.ds['close']) / 4
        elif src == 'hlc3':
            self.ds['hlc3'] = (self.ds['high'] + self.ds['low'] + self.ds['close']) / 3
        elif src == 'hl2':
            self.ds['hl2'] = (self.ds['high'] + self.ds['low']) / 2
        return src

    def calculate(self, ds:OHLCVDataset):
        self.ds = ds
        self.indicators()
        self.indicator_signals()
        self.signals()
        return self.ds

    def indicators(self):
        if self.ds.empty or not self.ds.ta:
            return
        self.ds.ta.macd(
            close=self.get_source(self.params['source']),
            fast=self.params['macd']['fast'], 
            slow=self.params['macd']['slow'], 
            signal=self.params['macd']['signal'],
            col_names=('macd', 'macd_diff', 'macd_signal'),
            append=True)
        self.ds.ta.stochrsi(
            close=self.get_source(self.params['source']),
            length=self.params['stochrsi']['length'],
            rsi_length=self.params['stochrsi']['rsi_length'],
            k=self.params['stochrsi']['k'],
            d=self.params['stochrsi']['d'],
            col_names=('stochrsi_k', 'stochrsi_d'),
            append=True)
        self.ds.ta.t3(
            close=self.get_source(self.params['source']),
            length=self.params['t3']['length'],
            a=self.params['t3']['a'],
            col_names=('t3',),
            append=True)

    def indicator_signals(self):
        if self.ds.empty:
            return
        self.ds['macd_buy']  = (self.ds['macd_diff'] > self.ds['macd_diff'].shift()) & (self.ds['macd_diff'] <= 0)
        self.ds['macd_sell'] = (self.ds['macd_diff'] < self.ds['macd_diff'].shift()) & (self.ds['macd_diff'] >= 0)

        self.ds['stochrsi_buy']  = self.ds['stochrsi_k'] > self.ds['stochrsi_d']
        self.ds['stochrsi_sell'] = self.ds['stochrsi_k'] < self.ds['stochrsi_d']

        self.ds['t3_buy']  = (self.ds['t3'] > self.ds['t3'].shift()) & (self.ds['t3'] >= 0)
        self.ds['t3_sell'] = (self.ds['t3'] < self.ds['t3'].shift()) & (self.ds['t3'] >= 0)
    
    def signals(self):
        if self.ds.empty:
            return
        self.ds['buy']  = self.ds['macd_buy'] & self.ds['stochrsi_buy'] & self.ds['t3_buy']
        self.ds['sell'] = self.ds['macd_sell'] & self.ds['stochrsi_sell'] & self.ds['t3_sell']
    
    def json(self):
        return {
            'name': self.name,
            'params': self.params
        }

