from markets.binance import BinanceMarket
from markets.interface import IMarket
from markets.kucoin import KucoinMarket
from markets.mexc import MEXCMarket
from logger import logger


def load_config(config_name) -> dict:
    import json
    with open('api.json', 'r') as f:
        config = json.load(f)
    return config.get(config_name, {})


def get_market(market_name, config={}) -> 'IMarket':
    if isinstance(config, str):
        config = load_config(config)
    if not isinstance(config, dict):
        logger.warning(f'Invalid config: {config}')
        config = {}
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
