from models import OHLCVDataset


class Strategy:
    params: dict
    name: str
    technical_name: str
    version: str
    ds: OHLCVDataset
    freq: str

    def __init__(self, params:dict|None=None) -> None:
        raise NotImplementedError

    def __call__(self, ds:OHLCVDataset) -> OHLCVDataset:
        """Compute defined indicators, generate indicator signals and then buy/sell signals based on those."""
        return self.calculate(ds)

    def default_params(self) -> dict:
        """Return a dict of default params for this strategy."""
        return {}

    def calculate(self, ds:OHLCVDataset) -> OHLCVDataset:
        """Compute defined indicators, generate indicator signals and then buy/sell signals based on those."""
        raise NotImplementedError

    def indicators(self) -> None:
        """Compute defined indicators and append to dataset."""
        raise NotImplementedError

    def indicator_signals(self) -> None:
        """Generate indicator signals based on indicators and append to dataset."""
        raise NotImplementedError

    def signals(self) -> None:
        """Generate buy/sell signals based on indicators and indicator signals and append to dataset."""
        raise NotImplementedError

    def json(self) -> dict:
        """Return a dict representation of this strategy."""
        return {
            'name': self.name,
            'technical_name': self.technical_name,
            'version': self.version,
            'params': self.params
        }

    def get_source(self, src = 'close'):
        """Calculates and adds a new column to the dataset based on the source."""
        if src == 'volume_ma':
            self.ds['volume_ma'] = self.ds['volume'].rolling(window=self.params['volume']['ma']).mean()
        elif src == 'ohlc4':
            self.ds['ohlc4'] = (self.ds['high'] + self.ds['low'] + self.ds['open'] + self.ds['close']) / 4
        elif src == 'hlc3':
            self.ds['hlc3'] = (self.ds['high'] + self.ds['low'] + self.ds['close']) / 3
        elif src == 'hl2':
            self.ds['hl2'] = (self.ds['high'] + self.ds['low']) / 2
        return src


def merge_dicts(d1, d2):
    # deep merge two dicts into a new one
    d = d1.copy()
    for k, v in d2.items():
        if k in d and isinstance(d[k], dict):
            d[k] = merge_dicts(d[k], v)
        else:
            d[k] = v
    return d
