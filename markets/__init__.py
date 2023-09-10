from .binance import BinanceMarket
from .kucoin import KucoinMarket
from .mexc import MEXCMarket

def get_market(market_name, config=None):
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