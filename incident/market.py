from incident.base import IssueBase
from incident.groups import Groups
import typing
if typing.TYPE_CHECKING:
    from quantapi.models import MarketAccount


class MarketBase(IssueBase):
    send_to = Groups.Everyone


class Market:
    class CandleFetchFailed(MarketBase):
        def __init__(self, market_name: str, exception: Exception):
            self.message = f'Failed to fetch candles from {market_name.upper()}: {exception!r}'
            super().__init__()

    class KeyExpired(MarketBase):
        def __init__(self, account: 'MarketAccount'):
            self.message = f'{account.market.exchange_name} MarketAccount ID={account.pk} credentials has expired.'
            super().__init__()

    class APIUnavailable(MarketBase):
        def __init__(self, market_name: str, exception: Exception):
            self.message = f'{market_name.upper()} API is unavailable: {exception!r}'
            super().__init__()
