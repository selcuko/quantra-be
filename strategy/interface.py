from models import OHLCVDataset


class Strategy:
    params: dict
    name: str
    ds: OHLCVDataset
    
    def __init__(self, params:dict=None) -> None:
        raise NotImplementedError
    
    def __call__(self, ds:OHLCVDataset) -> OHLCVDataset:
        """Compute defined indicators, generate indicator signals and then buy/sell signals based on those."""
        raise NotImplementedError
    
    def default_params(self) -> dict:
        """Return a dict of default params for this strategy."""
        raise NotImplementedError
    
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
        raise NotImplementedError
