from .binance import BinanceMarket


def get_market(market_name, config=None):
    if market_name == 'binance':
        return BinanceMarket(config)
    else:
        raise ValueError(f'Unknown market: {market_name}')


class MarketError(Exception):
    pass