from cache import get_interface, set_interface
from markets.binance import BinanceMarket
from markets.interface import IMarket
from markets.kucoin import KucoinMarket
from markets.mexc import MEXCMarket
from markets.bybit import BybitMarket
from markets.okx import OKXMarket
from markets.gateio import GateIOMarket

import typing
if typing.TYPE_CHECKING:
    from quantapi.models import MarketAccount, Market


def get_market(market_name, config=None, account:'MarketAccount|None'=None, market:'Market|None'=None) -> 'IMarket':
    if market and (iface := get_interface(market)):
        return iface
    market_map = { 
        'binance': BinanceMarket,
        'kucoin': KucoinMarket,
        'mexc': MEXCMarket,
        'bybit': BybitMarket,
        'okx': OKXMarket,
        'gateio': GateIOMarket,
    }
    if not isinstance(config, dict):
        config = {}
    market_name = market_name.lower()
    if market_name in market_map:
        market_instance:IMarket = market_map[market_name](config, account, market)
        market_instance.cache_to_db()
        if market:
            set_interface(market, market_instance)
        return market_instance
    else:
        raise ValueError(f'Unknown market: {market_name}, valid markets: {market_map.keys()}')
