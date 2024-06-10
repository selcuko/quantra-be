from datetime import datetime
import time
from typing import Callable
from unittest.mock import Mock

import pytz

from liveloop import LiveLoop
from loopgroup import LoopGroup
from markets.interface import IMarket
from quantapi.models import MarketAccount, MarketSymbol
from strategy.interface import Strategy


class MockIMarket(Mock, IMarket):
    def __init__(self, config, market) -> None:
        super().__init__()
        self.market = market

    def get_last_klines(self, symbol: MarketSymbol | str, interval: str, limit: int = 100, retry=1, silent=True) -> list[list]:
        return [[
            datetime(2024, 1, 1, tzinfo=pytz.UTC),  # open time
            '38000.0',  # open
            '38000.0',  # high
            '38000.0',  # low
            '38000.0',  # close
            '0.0',  # volume
        ]]

    def init_match_engine(self, symbol: str, interval: str, callback: Callable, liveloop: LiveLoop | LoopGroup | None):
        if not liveloop:
            return
        while not liveloop.should_stop():
            time.sleep(1)

    def cache_to_db(self, force=False):
        pass


class MockStrategy(Mock, Strategy):
    def __init__(self, params=None) -> None:
        super().__init__()

    def __call__(self, ds) -> None:
        ds['buy'] = False
        ds['sell'] = False
        return ds


class MockCache(Mock):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    @staticmethod
    def set(key, value, timeout=None):
        pass

    @staticmethod
    def get(key):
        pass


def mock_get_interface(account:MarketAccount):
    return MockIMarket({}, account.market)


def mock_get_strategy(name):
    return MockStrategy
