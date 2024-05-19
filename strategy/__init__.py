from typing import Type

from strategy.bb import StrategyBB

from .interface import Strategy
from .v1 import StrategyV1
from .v2 import StrategyV2


def get_strategy(name) -> Type[Strategy]:
    name = name.lower()
    strategies = {
        'v1': StrategyV1,
        'lisa': StrategyV1,
        'bb': StrategyBB,
        'azimuth': StrategyBB,
    }
    if name in strategies:
        return strategies[name]
    else:
        raise Exception(f'Unknown strategy {name}, available strategies are: {", ".join(strategies.keys())}')
