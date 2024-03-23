import pandas as pd

from indicators import MACD, T3, StochRSI
from models import OHLCVDataset
from strategy.interface import Strategy


class StrategyV2(Strategy):
    def __init__(self, params={}):
        self.params = {**self.default_params(), **params}
        self.name = 'StrategyV2.Lisa.NumPy'
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
                'length': 14,
                'rsi_length': 14,
                'k': 3,
                'd': 3
            },
            't3': {
                'length': 7,
                'a': 0.7
            }
        }
    
    def calculate(self, ds:OHLCVDataset):
        self.ds = ds
        self.indicators()
        self.indicator_signals()
        self.signals()
        return self.ds
    
    def indicators(self):
        MACD(
            self.ds, 
            n_fast=self.params['macd']['fast'], 
            n_slow=self.params['macd']['slow'], 
            n_signal=self.params['macd']['signal'], 
            inplace=True)
        StochRSI(
            self.ds, 
            rsi_length=self.params['stochrsi']['rsi_length'], 
            stoch_length=self.params['stochrsi']['length'], 
            smoothK=self.params['stochrsi']['k'], 
            smoothD=self.params['stochrsi']['d'], 
            inplace=True)
        T3(
            self.ds, 
            n=self.params['t3']['length'], 
            b=self.params['t3']['a'], 
            inplace=True)
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
        self.ds['buy'] = self.ds['macd_buy'] & self.ds['stochrsi_buy'] & self.ds['t3_buy']
        self.ds['sell'] = self.ds['macd_sell'] & self.ds['stochrsi_sell'] & self.ds['t3_sell']

    def json(self):
        return {
            'name': self.name,
            'params': self.params
        }
