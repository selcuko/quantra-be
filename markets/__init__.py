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
    authenticated: bool
    symbols: list[ExchangeSymbol]
    testnet: bool
    name: str
    spot_trading_enabled: bool
    def __init__(self, config:dict={}):
        """Initialize a market instance with config if provided."""
        pass
    def place_market_order(self, symbol:ExchangeSymbol|str, side:Literal['buy', 'sell'], funds:float=None, quantity:float=None) -> 'Order':
        """Place a market order and return an `Order` instance."""
        pass
    def place_limit_order(self, symbol:ExchangeSymbol|str, side:Literal['buy', 'sell'], price:float, quantity:float) -> 'Order':
        """Place a limit order and return an `Order` instance."""
        pass
    def get_order(self, symbol:ExchangeSymbol|str, order:Order|int) -> 'Order':
        """Get an order by id or `Order` instance and return an `Order` instance."""
        pass
    def get_orders(self, symbol:ExchangeSymbol|str) -> list['Order']:
        """Get all orders for a symbol and return a list of `Order` instances."""
        pass
    def get_open_orders(self, symbol:ExchangeSymbol|str=None) -> list['Order']:
        """Get all open orders and return a list of `Order` instances. You can optionally filter by symbol."""
        pass
    def cancel_order(self, symbol:ExchangeSymbol|str, order:Order|int) -> None:
        """Cancel an order by symbol and order id or `Order` instance. You can also call `order.cancel()` if you have an `Order` instance."""
        pass
    def cancel_all_orders(self, symbol:ExchangeSymbol|str=None) -> None:
        """Cancel all orders. You can optionally filter by symbol."""
        pass
    def get_klines(self, symbol:ExchangeSymbol|str, interval:str, start:datetime=None, end:datetime=None, limit:int=1000) -> list[list]:
        """Get klines for a symbol and return a list of lists. You can optionally filter by start, end and limit. If start and end are not provided, the last `limit` klines will be returned."""
        pass
    def get_symbols(self) -> list[ExchangeSymbol]:
        """Get all symbols and return a list of `ExchangeSymbol` instances."""
        pass
    def get_last_klines(self, symbol:ExchangeSymbol|str, interval:str, limit:int=1000) -> list[list]:
        """Get the last `limit` klines for a symbol and return a list of OHLCV candles."""
        pass

class MarketError(Exception):
    pass