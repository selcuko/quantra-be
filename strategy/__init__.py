from .v1 import StrategyV1
from .v2 import StrategyV2

def get_strategy(name, params={}):
    if name == 'v1':
        f = lambda ds: StrategyV1(ds, params)
        f.name = 'StrategyV1.Lisa.PandasTA'
        return f
    if name == 'v2':
        f = lambda ds: StrategyV2(ds, params)
        f.name = 'StrategyV2.Lisa.NumPy'
        return f
    else:
        raise Exception(f'Unknown strategy: {name}')