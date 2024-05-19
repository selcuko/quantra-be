import pandas as pd
from models import OHLCVDataset
from strategy.interface import Strategy, merge_dicts


class StrategyBB(Strategy):
    def __init__(self, params={}):
        self.params = merge_dicts(self.default_params(), params)
        self.name = 'Azimuth'
        self.technical_name = 'Bollinger Band Based Strategy'
        self.version = '1.0'
        self.ds = OHLCVDataset(pd.DataFrame())
        self.freq = ''

    def default_params(self):
        return {
            'bbands': {
                'length': 20,
                'stddev': 2
            },
            'source': 'close'
        }

    def indicators(self):
        if self.ds.empty or not self.ds.ta:
            return
        source = self.get_source(self.params['source'])
        basis = self.ds.ta.sma(
            close=source,
            length=self.params['bbands']['length']
        )
        deviation = self.ds.ta.stdev(
            close=source,
            length=self.params['bbands']['length']
        )
        upper = basis + deviation
        lower = basis - deviation
        self.ds['bb_upper'] = upper
        self.ds['bb_lower'] = lower

    def signals(self) -> None:
        if self.ds.empty:
            return
        shifted = self.ds.shift(1)
        self.ds['buy'] = (self.ds['close'] > self.ds['bb_upper']) & (shifted['close'] < shifted['bb_upper'])
        self.ds['sell'] = (self.ds['close'] < self.ds['bb_lower']) & (shifted['close'] > shifted['bb_lower'])

    def calculate(self, ds: OHLCVDataset) -> OHLCVDataset:
        self.ds = ds
        if self.freq:
            self.ds.change(self.freq)
        self.indicators()
        self.signals()
        return self.ds
