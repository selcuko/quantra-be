from .v1 import StrategyV1
from .v2 import StrategyV2

def get_strategy(name, params={}):
    if name == 'v1':
        return lambda ds: StrategyV1(ds, params)
    if name == 'v2':
        return lambda ds: StrategyV2(ds, params)
    else:
        raise Exception(f'Unknown strategy: {name}')