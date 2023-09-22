from models import OHLCVDataset
from .v1 import StrategyV1
from .v2 import StrategyV2

class Strategy:
    params: dict
    name: str
    ds: OHLCVDataset
    def __init__(self) -> None:
        pass
    def __call__(self, ds:OHLCVDataset) -> OHLCVDataset:
        """Compute defined indicators, generate indicator signals and then buy/sell signals based on those."""
        pass
    def default_params(self) -> dict:
        """Return a dict of default params for this strategy."""
        pass
    def calculate(self, ds:OHLCVDataset) -> OHLCVDataset:
        """Compute defined indicators, generate indicator signals and then buy/sell signals based on those."""
        pass
    def indicators(self) -> None:
        """Compute defined indicators and append to dataset."""
        pass
    def indicator_signals(self) -> None:
        """Generate indicator signals based on indicators and append to dataset."""
        pass
    def signals(self) -> None:
        """Generate buy/sell signals based on indicators and indicator signals and append to dataset."""
        pass
    def json(self) -> dict:
        """Return a dict representation of this strategy."""
        pass


def get_strategy(name) -> Strategy:
    if name == 'v1':
        return StrategyV1
    if name == 'v2':
        return StrategyV2
    else:
        raise Exception(f'Unknown strategy: {name}')