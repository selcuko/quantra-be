from datetime import datetime
import time
from typing import Callable, Literal
from unittest.mock import Mock

import pytz

from liveloop import LiveLoop
from loopgroup import LoopGroup
from markets.errors import InsufficientBalance
from markets.interface import IMarket
from quantapi.models import MarketAccount, MarketSymbol, Order
from strategy.interface import Strategy


class MockIMarket(Mock, IMarket):
    def __init__(self, config, account, **kwargs) -> None:
        super().__init__(config, account, **kwargs)
        self.account = account
        self.market = account.market
        self.capital = 10
        self.assets = {
            'BTC': 0.1
        }

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

    def place_market_order(self, symbol: MarketSymbol | str, side: Literal['buy'] | Literal['sell'], funds: str | None = None, quantity: str | None = None, validate=True) -> Order:
        if isinstance(symbol, str):
            symbol = MarketSymbol.objects.get(name=symbol, market=self.market)
        if side == 'buy' and self.capital < float(funds or 0):
            raise InsufficientBalance
        if side == 'sell' and self.assets[symbol.base] < float(quantity or 0):
            raise InsufficientBalance
        return Order(
            symbol=symbol,
            side=side.upper(),
            deal_funds=float(funds) if funds else 1,
            deal_size=float(quantity) if quantity else 1,
            status='FILLED',
        )


class MockResponse(Mock):
    def __init__(self, **kwargs) -> None:
        super().__init__()
        self.kwargs = kwargs
        self.status_code = kwargs.get('code', 200)
        self.body = kwargs.get('body', {})

    def json(self):
        return self.body


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
    return MockIMarket({}, account)


def mock_get_strategy(name):
    return MockStrategy
