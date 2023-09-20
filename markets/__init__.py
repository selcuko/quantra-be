from datetime import datetime
from typing import Literal

from models import ExchangeSymbol, Order
from .binance import BinanceMarket
from .kucoin import KucoinMarket
from .mexc import MEXCMarket

def get_market(market_name, config={}) -> 'Market':
    market_name = market_name.lower()
    if market_name == 'binance':
        return BinanceMarket(config)
    elif market_name == 'kucoin':
        return KucoinMarket(config)
    elif market_name == 'mexc':
        return MEXCMarket(config)
    else:
        raise ValueError(f'Unknown market: {market_name}')


class Market:
    def __init__(self, config={}):
        pass
    def place_market_order(self, symbol:ExchangeSymbol|str, side:Literal['buy', 'sell'], funds:float=None, quantity:float=None) -> 'Order':
        pass
    def place_limit_order(self, symbol:ExchangeSymbol|str, side:Literal['buy', 'sell'], price:float, quantity:float) -> 'Order':
        pass
    def get_order(self, symbol:ExchangeSymbol|str, order:Order|int) -> 'Order':
        pass
    def get_orders(self, symbol:ExchangeSymbol|str, limit:int=100) -> list['Order']:
        pass
    def get_open_orders(self, symbol:ExchangeSymbol|str=None, limit:int=100) -> list['Order']:
        pass
    def cancel_order(self, symbol:ExchangeSymbol|str, order:Order|int) -> None:
        pass
    def cancel_all_orders(self, symbol:ExchangeSymbol|str=None) -> None:
        pass
    def get_klines(self, symbol:ExchangeSymbol|str, interval:str, start:datetime=None, end:datetime=None, limit:int=1000) -> list[list]:
        pass
    def get_symbols(self) -> list[ExchangeSymbol]:
        pass
    def get_last_klines(self, symbol:ExchangeSymbol|str, interval:str, limit:int=1000) -> list[list]:
        pass

class MarketError(Exception):
    pass