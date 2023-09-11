from .v1 import StrategyV1

def get_strategy(name, params={}):
    if name == 'v1':
        return lambda ds: StrategyV1(ds, params)
    else:
        raise Exception(f'Unknown strategy: {name}')