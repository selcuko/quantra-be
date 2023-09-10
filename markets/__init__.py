from .binance import BinanceMarket
from .kucoin import KucoinMarket


def get_market(market_name, config=None):
    market_name = market_name.lower()
    if market_name == 'binance':
        return BinanceMarket(config)
    elif market_name == 'kucoin':
        return KucoinMarket(config)
    else:
        raise ValueError(f'Unknown market: {market_name}')


class MarketError(Exception):
    pass