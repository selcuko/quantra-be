from .v1 import StrategyV1
from .v2 import StrategyV2

def get_strategy(name):
    if name == 'v1':
        return StrategyV1
    if name == 'v2':
        return StrategyV2
    else:
        raise Exception(f'Unknown strategy: {name}')