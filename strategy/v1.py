from models import OHLCVDataset
import pandas_ta

class StrategyV1:
    def __init__(self, params={}):
        self.params = {**self.default_params(), **params}
        self.name = 'StrategyV1.Lisa.PandasTA'
        self.ds = None
    
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
        self.ds.ta.macd(
            fast=self.params['macd']['fast'], 
            slow=self.params['macd']['slow'], 
            signal=self.params['macd']['signal'],
            col_names=('macd', 'macd_signal', 'macd_diff'),
            append=True)
        self.ds.ta.stochrsi(
            length=self.params['stochrsi']['length'],
            rsi_length=self.params['stochrsi']['rsi_length'],
            k=self.params['stochrsi']['k'],
            d=self.params['stochrsi']['d'],
            col_names=('stochrsi_k', 'stochrsi_d'),
            append=True)
        self.ds.ta.t3(
            length=self.params['t3']['length'],
            a=self.params['t3']['a'],
            col_names=('t3',),
            append=True)

    def indicator_signals(self):
        self.ds['macd_buy']  = (self.ds['macd_diff'] > self.ds['macd_diff'].shift()) & (self.ds['macd_diff'] <= 0)
        self.ds['macd_sell'] = (self.ds['macd_diff'] < self.ds['macd_diff'].shift()) & (self.ds['macd_diff'] >= 0)

        self.ds['stochrsi_buy']  = self.ds['stochrsi_k'] > self.ds['stochrsi_d']
        self.ds['stochrsi_sell'] = self.ds['stochrsi_k'] < self.ds['stochrsi_d']

        self.ds['t3_buy']  = (self.ds['t3'] > self.ds['t3'].shift()) & (self.ds['t3'] >= 0)
        self.ds['t3_sell'] = (self.ds['t3'] < self.ds['t3'].shift()) & (self.ds['t3'] >= 0)
    
    def signals(self):
        self.ds['buy']  = self.ds['macd_buy'] & self.ds['stochrsi_buy'] & self.ds['t3_buy']
        self.ds['sell'] = self.ds['macd_sell'] & self.ds['stochrsi_sell'] & self.ds['t3_sell']

