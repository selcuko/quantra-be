from typing import Type

from .interface import Strategy
from .v1 import StrategyV1
from .v2 import StrategyV2


def get_strategy(name) -> Type[Strategy]:
    strategies = {
        'v1': StrategyV1,
        'StrategyV1.Lisa.PandasTA': StrategyV1,
        'v2': StrategyV2,
        'StrategyV2.Lisa.NumPy': StrategyV2,
    }
    if name in strategies:
        return strategies[name]
    else:
        raise Exception(f'Unknown strategy {name}, available strategies are: {", ".join(strategies.keys())}')
