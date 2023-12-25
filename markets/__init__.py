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
    testnet: bool
    name: str
    symbols: dict[str, ExchangeSymbol]
    spot_trading_enabled: bool
    capital: float
    assets: dict[str, float]
    commission: dict[str, float]
    def __init__(self, config:dict={}):
        """Initialize a market instance with config if provided."""
        pass
    
    def json(self) -> dict:
        """Return a dict/JSON for this instance. Serialization done whenever necessary.

        Returns:
            dict: dict representing this market instance
        """
    
    def get_account(self):
        """Sets capital, assets etc. on market instance."""

    def place_market_order(self, symbol:ExchangeSymbol|str, side:Literal['buy', 'sell'], funds:float=None, quantity:float=None, validate=True) -> 'Order':
        """Place a market order, fetch the order back from market

        Args:
            symbol (ExchangeSymbol | str): symbol object or symbol name
            side ('buy' | 'sell'): side of order
            funds (float, optional): funds or quantity is required. Defaults to None.
            quantity (float, optional): funds or quantity is required. Defaults to None.
            validate (bool, optional): validate if the order made it to exchange. Defaults to True

        Returns:
            Order: Order object
        """
    
    def place_limit_order(self, symbol:ExchangeSymbol|str, side:Literal['buy', 'sell'], price:float, quantity:float, validate=True) -> 'Order':
        """Place a limit order, fetch the order back from market

        Args:
            symbol (ExchangeSymbol | str): symbol object or symbol name
            side ('buy' | 'sell'): side of order
            price (float): price for order
            quantity (float): quantity for order
            validate (bool, optional): validate if the order made it to exchange. Defaults to True

        Returns:
            Order: Order object
        """
    
    def get_order(self, symbol:ExchangeSymbol|str, order:Order|int) -> 'Order':
        """Get order from market

        Args:
            symbol (ExchangeSymbol | str): ExchangeSymbol object or name of symbol
            order (Order | int): Order object or ID of order

        Returns:
            Order: Order object
        """
        
    def get_orders(self, symbol:ExchangeSymbol|str) -> list['Order']:
        """Get all orders for given symbol

        Args:
            symbol (ExchangeSymbol | str): ExchangeSymbol object or name of symbol

        Returns:
            list[Order]: list of Order objects
        """
        
    def get_open_orders(self, symbol:ExchangeSymbol|str=None) -> list['Order']:
        """Get all open orders

        Args:
            symbol (ExchangeSymbol | str, optional): ExchangeSymbol object or name of symbol
        
        Returns:
            list[Order]: list of Order objects
        """
        
    def cancel_order(self, symbol:ExchangeSymbol|str, order:Order|int) -> 'Order':
        """Cancel an order given symbol

        Args:
            symbol (ExchangeSymbol | str): ExchangeSymbol object or name of symbol
            order (Order | int): Order object or ID of order

        Returns:
            Order: Order object
        """                
    
    def cancel_all_orders(self, symbol:ExchangeSymbol|str=None) -> list['Order']:
        """Cancel all orders for given symbol

        Args:
            symbol (ExchangeSymbol | str, optional): ExchangeSymbol object or name of symbol

        Returns:
            list[Order]: list of Order objects
        """

    def get_earliest__valid_timestamp(self, symbol:str, interval:str, start:datetime) -> datetime:
        """Get the earliest timestamp that is valid for given symbol and interval

        Args:
            symbol (str): symbol name
            interval (str): in "1 min" format
            start (datetime): tzinfo is required

        Returns:
            datetime: earliest datetime
        """
        
    def get_klines(self, symbol:ExchangeSymbol|str, interval:str, start:datetime=None, end:datetime=None, limit:int=1000, retry=0) -> list[list]:
        """Get historical candle data.

        Args:
            symbol (ExchangeSymbol | str)
            interval (str): in "1 min" format
            start (datetime, optional): tzinfo is required if supplied. Defaults to None.
            end (datetime, optional): tzinfo is required if supplied. Defaults to None.
            limit (int, optional): Defaults to 1000.
            retry (int, optional): Retry attempts. Defaults to 0.

        Returns:
            list[list]: list of OHLCV candles
        """
        
    def get_symbols(self) -> list[ExchangeSymbol]:
        """Get a list of symbols present in this market

        Returns:
            list[ExchangeSymbol]: list of ExchangeSymbol object
        """
        
    def get_last_klines(self, symbol:ExchangeSymbol|str, interval:str, limit:int=100, retry=1, silent=True) -> list[list]:
        """Get last n candles for given symbol

        Args:
            symbol (ExchangeSymbol | str)
            interval (str): in "1 min" format
            limit (int, optional): get this many candles. Defaults to 100.
            retry (int, optional): number of retries will there be a failure. Defaults to 1.
            silent (bool, optional): raise an exception after retry attempts end. Defaults to True.

        Returns:
            list[list]: list of OHLCV candles
        """


class MarketError(Exception):
    pass
