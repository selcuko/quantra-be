from markets.binance import BinanceMarket
from markets.interface import IMarket
from markets.kucoin import KucoinMarket
from markets.mexc import MEXCMarket
from markets.bybit import BybitMarket
from markets.okx import OKXMarket

import typing
if typing.TYPE_CHECKING:
    from quantapi.models import Market as DBMarket


def get_market(market_name, config=None, market:'DBMarket|None'=None) -> 'IMarket':
    market_map = { 
        'binance': BinanceMarket,
        'kucoin': KucoinMarket,
        'mexc': MEXCMarket,
        'bybit': BybitMarket,
        'okx': OKXMarket,
    }
    if not isinstance(config, dict):
        config = {}
    market_name = market_name.lower()
    if market_name in market_map:
        market_instance:IMarket = market_map[market_name](config, market)
        market_instance.cache_to_db()
        return market_instance
    else:
        raise ValueError(f'Unknown market: {market_name}, valid markets: {market_map.keys()}')
