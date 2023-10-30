from markets.binance import BinanceMarket
from markets.interface import IMarket
from markets.kucoin import KucoinMarket
from markets.mexc import MEXCMarket


def get_market(market_name, config=None) -> 'IMarket':
    market_map = { 'binance': BinanceMarket,
                   'kucoin': KucoinMarket,
                   'mexc': MEXCMarket }
    if not isinstance(config, dict):
        config = {}
    market_name = market_name.lower()
    if market_name in market_map:
        return market_map[market_name](config)
    else:
        raise ValueError(f'Unknown market: {market_name}, valid markets: {market_map.keys()}')
