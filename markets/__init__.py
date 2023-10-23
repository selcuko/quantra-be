from markets.binance import BinanceMarket
from markets.interface import IMarket
from markets.kucoin import KucoinMarket
from markets.mexc import MEXCMarket


def get_market(market_name, config={}) -> 'IMarket':
    market_name = market_name.lower()
    if market_name == 'binance':
        return BinanceMarket(config)
    elif market_name == 'kucoin':
        return KucoinMarket(config)
    elif market_name == 'mexc':
        return MEXCMarket(config)
    else:
        raise ValueError(f'Unknown market: {market_name}')


class MarketError(Exception):
    pass
