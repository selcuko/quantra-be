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
    market_map = {
        'binance': BinanceMarket,
        'kucoin': KucoinMarket,
        'mexc': MEXCMarket,
    }
    if isinstance(config, str):
        config = load_config(config)
    if not isinstance(config, dict):
        logger.warning(f'Invalid config: {config}')
        config = {}
    market_name = market_name.lower()
    if market_name in market_map:
        return market_map[market_name](config)
    else:
        raise ValueError(f'Unknown market: {market_name}, valid markets: {market_map.keys()}')

