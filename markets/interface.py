from datetime import datetime
import json
from typing import TYPE_CHECKING, Callable, Literal, Optional
from django.utils import timezone
if TYPE_CHECKING:
    from quantapi.models import Order, MarketSymbol, Market as DBMarket


class IMarket:
    authenticated: bool
    testnet: bool
    name: str
    symbols: dict[str, 'MarketSymbol']
    spot_trading_enabled: bool
    capital: float
    assets: dict[str, float]
    commission: dict[str, float]
    market: Optional['DBMarket']
    def __init__(self, config:Optional[dict]=None, market:Optional['DBMarket']=None):
        """Initialize a market instance with config if provided."""
        raise NotImplementedError
    
    def json(self) -> dict:
        """Return a dict/JSON for this instance. Serialization done whenever necessary.

        Returns:
            dict: dict representing this market instance
        """
        raise NotImplementedError(f'{self.name} does not implement json()')

    def format_candle(self, candle:list) -> dict:
        """Format candle to standard format

        Args:
            candle (list): list of OHLCV

        Returns:
            dict: standard candle
        """
        
        candle = {
            'time': candle[0],
            'open': candle[1],
            'high': candle[2],
            'low': candle[3],
            'close': candle[4],
            'volume': candle[5] if len(candle) > 5 else None,
        }
        candle['price'] = (candle['open'] + candle['close'] + candle['high'] + candle['low']) / 4
        return candle

    def init_match_engine(self, symbol:str, interval:str, callback:Callable):
        """Blocking (sync) function to initialize a match engine for given symbol and interval. Run in a thread!

        Args:
            symbol (str): symbol name
            interval (str): in "1 min" format

        Returns:
            str: websocket uri
        """
        raise NotImplementedError(f'{self.name} does not implement init_match_engine()')

    def init_websocket(self, symbol:str, interval:str, callback:Callable):
        """Blocking (sync) function to initialize a websocket for given symbol and interval. Run in a thread!

        Args:
            symbol (str): symbol name
            interval (str): in "1 min" format

        Returns:
            str: websocket uri
        """
        raise NotImplementedError(f'{self.name} does not implement get_websocket_uri()')
    
    def format_ws_candle(self, payload:dict) -> dict:
        """Format websocket candle payload to standard format

        Args:
            payload (dict): websocket payload

        Returns:
            dict: standard candle
        """
        raise NotImplementedError(f'{self.name} does not implement format_ws_candle()')

    def get_account(self):
        """Sets capital, assets etc. on market instance."""
        raise NotImplementedError(f'{self.name} does not implement get_account()')

    def has_symbol(self, symbol:str) -> bool:
        """Check if symbol is present in this market

        Args:
            symbol (str): symbol name

        Returns:
            bool: True if symbol is present
        """
        raise NotImplementedError

    def place_market_order(self, symbol:'MarketSymbol|str', side:Literal['buy', 'sell'], funds:Optional[float]=None, quantity:Optional[float]=None, validate=True) -> 'Order':
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
        raise NotImplementedError

    def place_limit_order(self, symbol:'MarketSymbol|str', side:Literal['buy', 'sell'], price:float, quantity:float, validate=True) -> 'Order':
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
        raise NotImplementedError

    def get_order(self, symbol:'MarketSymbol|str', order:'Order|int') -> 'Order':
        """Get order from market

        Args:
            symbol (ExchangeSymbol | str): ExchangeSymbol object or name of symbol
            order (Order | int): Order object or ID of order

        Returns:
            Order: Order object
        """
        raise NotImplementedError

    def get_orders(self, symbol:'MarketSymbol|str') -> list['Order']:
        """Get all orders for given symbol

        Args:
            symbol (ExchangeSymbol | str): ExchangeSymbol object or name of symbol

        Returns:
            list[Order]: list of Order objects
        """
        raise NotImplementedError

    def get_open_orders(self, symbol:'MarketSymbol|str') -> list['Order']:
        """Get all open orders

        Args:
            symbol (ExchangeSymbol | str, optional): ExchangeSymbol object or name of symbol
        
        Returns:
            list[Order]: list of Order objects
        """
        raise NotImplementedError

    def cancel_order(self, symbol:'MarketSymbol|str', order:'Order|int') -> 'Order':
        """Cancel an order given symbol

        Args:
            symbol (ExchangeSymbol | str): ExchangeSymbol object or name of symbol
            order (Order | int): Order object or ID of order

        Returns:
            Order: Order object
        """           
        raise NotImplementedError     

    def cancel_all_orders(self, symbol:Optional['MarketSymbol|str']) -> list['Order']:
        """Cancel all orders for given symbol

        Args:
            symbol (ExchangeSymbol | str, optional): ExchangeSymbol object or name of symbol

        Returns:
            list[Order]: list of Order objects
        """
        raise NotImplementedError

    def get_klines(self, symbol:'MarketSymbol|str', interval:str, start:datetime, end:Optional[datetime]=None, limit:int=1000, retry=0) -> list[list]:
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
        raise NotImplementedError

    def get_symbols(self) -> list['MarketSymbol']:
        """Get a list of symbols present in this market

        Returns:
            list[ExchangeSymbol]: list of ExchangeSymbol object
        """
        raise NotImplementedError

    def get_last_klines(self, symbol:'MarketSymbol|str', interval:str, limit:int=100, retry=1, silent=True) -> list[list]:
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
        raise NotImplementedError

    
    def get_current_prices(self, save=True) -> dict:
        raise NotImplemented

    def get_equity(self, save=True) -> float:
        raise NotImplemented

    def cache_to_db(self):
        if self.market:
            self.market.usdt = self.capital
            self.market.assets = json.dumps(self.assets)
            self.market.assets_updated_at = timezone.now()
            self.get_current_prices(save=False)
            self.get_equity(save=False)
            self.market.save()
        return

