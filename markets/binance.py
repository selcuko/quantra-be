import json
import time
import typing
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable, Literal, Optional

import pytz
import requests
from binance.client import Client
from django.utils import timezone

from logger import logger
from markets.errors import (InsufficientBalance, KlineFetchFailed,
                            MarketAPIError, OrderPlacementError,
                            OrderPostProcessingError, RejectedOrder)
from markets.helper import authentication_required, float_to_precision
from markets.interface import IMarket
from match import MatchEngine
from models import interval_to_minutes

if typing.TYPE_CHECKING:
    from quantapi.models import MarketSymbol, Order, MarketAccount
    from liveloop import LiveLoop


from websockets.exceptions import ConnectionClosed, ConnectionClosedOK
from websockets.sync.client import connect


class BinanceMarket(IMarket):
    name = 'Binance'

    def __init__(self, config, account:'MarketAccount'):
        if config is None:
            config = {}
        self.authenticated = bool(config.get('API_KEY') and config.get('API_SECRET'))
        self.testnet = False
        self.spot_trading_enabled = False
        self.capital = 0
        self.assets = {}
        self.commission = {}
        self.account = account
        self.market = self.account.market
        self.stop_websocket_stream = False
        if self.authenticated:
            self.testnet = config.get('TESTNET', False)
            self.client = Client(
                api_key=config['API_KEY'],
                api_secret=config['API_SECRET'],
                testnet=self.testnet)
        else:
            self.client = Client()
        self.symbols = self.get_symbols()
        if self.authenticated:
            self.get_account()

    def get_websocket_uri(self, symbol:'MarketSymbol|str', interval:str) -> str:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        symbol_name = self._format_symbol(symbol.name).lower()
        return f'wss://stream.binance.com:9443/ws/{symbol_name}@kline_{self._format_interval(interval)}'

    def format_ws_candle(self, payload:dict) -> dict:
        candle = payload['k']
        return {
            'time': datetime.fromtimestamp(candle['t']/1000, tz=pytz.UTC).replace(second=0, microsecond=0),
            'start': datetime.fromtimestamp(candle['t']/1000, tz=pytz.UTC).replace(second=0, microsecond=0),
            'end': datetime.fromtimestamp(candle['T']/1000, tz=pytz.UTC).replace(second=0, microsecond=0),
            'open': float(candle['o']),
            'high': float(candle['h']),
            'low': float(candle['l']),
            'close': float(candle['c']),
            'volume': float(candle['v']),
            'trades': int(candle['n']),
            'last': candle['x'],
            'quote_asset_volume': float(candle['q']),
            'taker_buy_base_asset_volume': float(candle['V']),
            'taker_buy_quote_asset_volume': float(candle['Q']),
        }

    @staticmethod
    def format_match(payload:dict) -> dict:
        return {
            'time': datetime.fromtimestamp(payload['E']/1000, tz=pytz.UTC).replace(second=0, microsecond=0),
            'price': float(payload['p']),
            'size': float(payload['q']),
            'maker': payload['m'],
        }

    def init_match_engine(self, symbol:str, interval:str, callback:Callable, liveloop:'LiveLoop|None'):
        ws_uri = f'wss://stream.binance.com:9443/ws/{self._format_symbol(symbol).lower()}@trade'
        ws = connect(ws_uri)
        me = MatchEngine(interval, callback)
        last_ping = datetime.now()
        retries = 0
        while not self.stop_websocket_stream:
            if liveloop and liveloop.should_stop():
                self.stop_websocket_stream = True
                break
            if (datetime.now() - last_ping) > timedelta(seconds=30):
                ws.pong()
                last_ping = datetime.now()
            try:
                data = json.loads(ws.recv(timeout=10))
                retries = 0
                match = self.format_match(data)
                me.on_match(match)
            except TimeoutError:
                continue
            except (ConnectionClosed, ConnectionClosedOK):
                time.sleep(5)
                ws = connect(ws_uri)
                continue
            except Exception as e:
                if retries > self.WS_MAX_RETRIES:
                    msg = f'Cannot start websocket connection for match engine for {symbol} on {self.name} (tried {retries} times).'
                    logger.error(msg, exc_info=True)
                    raise MarketAPIError(msg) from e
                retries += 1
                time.sleep(5)
                ws = connect(ws_uri)
                continue

    def init_websocket(self, symbol:str, interval:str, callback:Callable, liveloop:'LiveLoop', retries=0):
        ws_uri = self.get_websocket_uri(symbol, interval)
        try:
            ws = connect(ws_uri)
            while not self.stop_websocket_stream and not liveloop.should_stop():
                ws.pong()
                try:
                    data = json.loads(ws.recv(timeout=10))
                except TimeoutError:
                    continue
                candle = self.format_ws_candle(data)
                if candle['last']:
                    callback(candle)
        except:
            if retries < self.WS_MAX_RETRIES:
                retries += 1
                time.sleep(1)
                return self.init_websocket(symbol, interval, callback, liveloop, retries)
            msg = f'Cannot start websocket connection for {symbol} on {self.name} (tried {retries} times).'
            logger.error(msg, exc_info=True)
            raise MarketAPIError(msg)

    def _standardize_klines(self, klines:list[list]) -> list[list]:
        return [[
            self._standardize_datetime(kline[0]),
            float(kline[1]),
            float(kline[2]),
            float(kline[3]),
            float(kline[4]),
            float(kline[5]),
        ] for kline in klines ]

    @staticmethod
    def _standardize_symbol(symbol:str) -> str:
        return symbol.replace('-', '').replace('USDT', '-USDT').upper()

    @staticmethod
    def _standardize_datetime(dtstr:str) -> datetime:
        return datetime.fromtimestamp(int(dtstr) // 1000, tz=pytz.UTC).replace(second=0, microsecond=0)

    @staticmethod
    def _format_symbol(symbol:str) -> str:
        assert '-' in symbol, f'Symbol must be in the format BASE-QUOTE (e.g. BTC-USDT), you provided: "{symbol}"'
        symbol = symbol.replace('-', '').upper()
        return symbol

    @staticmethod
    def _format_interval(interval:str) -> str:
        return {
            '1 min': Client.KLINE_INTERVAL_1MINUTE,
            '3 min': Client.KLINE_INTERVAL_3MINUTE,
            '5 min': Client.KLINE_INTERVAL_5MINUTE,
            '15 min': Client.KLINE_INTERVAL_15MINUTE,
            '30 min': Client.KLINE_INTERVAL_30MINUTE,
            '1 hour': Client.KLINE_INTERVAL_1HOUR,
            '2 hour': Client.KLINE_INTERVAL_2HOUR,
            '4 hour': Client.KLINE_INTERVAL_4HOUR,
            '6 hour': Client.KLINE_INTERVAL_6HOUR,
            '8 hour': Client.KLINE_INTERVAL_8HOUR,
            '12 hour': Client.KLINE_INTERVAL_12HOUR,
            '1 day': Client.KLINE_INTERVAL_1DAY,
            '3 day': Client.KLINE_INTERVAL_3DAY,
            '1 week': Client.KLINE_INTERVAL_1WEEK,
            '1 month': Client.KLINE_INTERVAL_1MONTH,
        }[interval]

    @staticmethod
    def _format_datetime(dt) -> str:
        return str(int(dt.replace(second=0, microsecond=0).timestamp()*1000))

    def has_symbol(self, symbol_name:str) -> bool:
        if not self.symbols:
            self.symbols = self.get_symbols()
        return symbol_name in self.symbols

    def _get_symbol_from_name(self, symbol_name:str) -> 'MarketSymbol':
        try:
            _symbol = symbol_name
            return self.symbols[_symbol]
        except KeyError:
            logger.error(f'Symbol {symbol_name} is not present in {self.name}: {self.symbols.keys()}')
            raise ValueError(f'Symbol {symbol_name} is not present in {self.name}')

    def _prep_symbol(self, symbol:dict) -> 'MarketSymbol':
        from quantapi.models import MarketSymbol
        exc_symbol = MarketSymbol(
                market=self.market,
                name=self._standardize_symbol(symbol['symbol']),
                base=symbol['baseAsset'],
                quote=symbol['quoteAsset'],
                base_precision=symbol['baseAssetPrecision'],
                quote_precision=symbol['quotePrecision'],
                spot_trading_enabled=symbol['isSpotTradingAllowed'],
                margin_trading_enabled=symbol.get('isMarginTradingAllowed', False),
                details=json.dumps(symbol))
        return exc_symbol

    @staticmethod
    def _prep_order(order:dict) -> 'Order':
        from quantapi.models import Order
        order_time = order.get('time') or order.get('workingTime') or order.get('transactTime') or order.get('updateTime') or 0
        return Order(
            oid=order['orderId'],
            client_oid=order['clientOrderId'],
            order_type=order['type'].upper(),
            price=float(order['price']),
            market_timestamp=datetime.fromtimestamp(int(order_time // 1000), tz=pytz.UTC),
            deal_funds=float(order.get('cummulativeQuoteQty', 0)),
            deal_size=float(order.get('origQty', 0)),
            status=order['status'].upper(),
            funds=float(order.get('origQuoteOrderQty', 0)),
            details=json.dumps(order),
            side=order['side'].upper(),
        )

    def _get_klines(self, symbol:str, interval:str, start:datetime, end:Optional[datetime]=None, limit=1000, retry=0) -> list[list]:
        if end:
            calculated_end = end
        else:
            calculated_end = start + timedelta(minutes=interval_to_minutes(interval) * limit)
        try:
            klines = self.client.get_historical_klines(
                        symbol=self._format_symbol(symbol),
                        interval=self._format_interval(interval),
                        start_str=self._format_datetime(start),
                        end_str=self._format_datetime(calculated_end),
                        limit=limit)
        except Exception as e:
            logger.error(f'Error fetching klines for {symbol} from {self.name}', exc_info=True)
            if retry > 0:
                logger.warning(f'Retrying {retry} more times')
                time.sleep(1)
                return self._get_klines(symbol, interval, start, end, limit, retry-1)
            raise
        return self._standardize_klines(klines)

    def get_klines(self, symbol:str, interval:str, start:datetime, end:Optional[datetime]=None, limit=1000, retry=0) -> list[list]:
        if symbol not in self.symbols:
            raise ValueError(f'Symbol {symbol} is not present on {self.name}')
        try:
            return self._get_klines(symbol, interval, start, end, limit, retry=retry)
        except requests.exceptions.ConnectionError:
            return []

    def get_earliest_valid_timestamp(self, symbol, interval):
        return self.client._get_earliest_valid_timestamp(symbol, interval)

    def get_last_klines(self, symbol:str, interval:str, limit=100, retry=1, silent=True) -> list[list]:
        minutes = interval_to_minutes(interval)
        now = datetime.now(tz=pytz.UTC) + timedelta(minutes=1)
        start = now - timedelta(minutes=minutes*limit+1)
        klines = self.get_klines(symbol, interval, start, now, limit=limit*2)
        if not klines:
            return []
        last_kline_dt = klines[-1][0]
        if (now - last_kline_dt) > timedelta(minutes=minutes*2):
            error = f'Last kline dt {last_kline_dt} does not match current time {now}, total klines: {len(klines)}, {start} -> {now}'
            if retry > 0:
                time.sleep(1)
                return self.get_last_klines(symbol, interval, limit, retry-1, silent)
            if not silent:
                raise KlineFetchFailed(error)
        return klines

    def get_symbols(self) -> dict[str, 'MarketSymbol']:
        from quantapi.models import MarketSymbol
        exchange_info = self.client.get_exchange_info()
        self.symbols = { self._standardize_symbol(symbol['symbol']): self._prep_symbol(symbol) for symbol in exchange_info.get('symbols', []) }
        self.symbols = { key: value for key, value in self.symbols.items() if value.quote == 'USDT'}
        if self.market: 
            MarketSymbol.objects.bulk_create(self.symbols.values(), update_conflicts=True, update_fields=[
                'spot_trading_enabled', 
                'margin_trading_enabled', 
                'details',
                'base_precision',
                'quote_precision',
            ], unique_fields=['name', 'market'])
        return self.symbols

    @authentication_required
    def place_market_order(self, symbol:'MarketSymbol|str', side:Literal['buy', 'sell'], funds:Optional[str]=None, quantity:Optional[str]=None, validate=True) -> 'Order':
        initial_quantity = quantity
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        client_oid = uuid.uuid4().hex
        try:
            _order_payload = self.client.order_market(
                side=side,
                symbol=self._format_symbol(symbol.name),
                quantity=quantity,
                quoteOrderQty=funds,
                newClientOrderId=client_oid)
        except Exception as e:
            if 'filter failure' in str(e).lower():
                raise RejectedOrder(f'Order was rejected by the exchange: {e}')
            elif 'insufficient' in str(e).lower():
                raise InsufficientBalance(f'Insufficient funds to place order on {self.name}')
            raise OrderPlacementError(f'Error placing order: {e!r}')
        try:
            order = self._prep_order(_order_payload)
        except Exception as e:
            raise OrderPostProcessingError(e, oid=_order_payload.get('orderId'))
        return order

    @authentication_required
    def place_limit_order(self, symbol:'MarketSymbol|str', side:Literal['buy', 'sell'], price:float, quantity:float, validate=True) -> 'Order':
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        client_oid = uuid.uuid4().hex
        if symbol.base_precision:
            float_to_precision(Decimal(quantity), Decimal(symbol.base_precision))
        if symbol.quote_precision:
            price = float_to_precision(Decimal(price), Decimal(symbol.quote_precision))
        try:
            order = self.client.order_limit(
                side=side,
                symbol=self._format_symbol(symbol.name),
                price=price,
                quantity=quantity,
                newClientOrderId=client_oid)
            logger.info(f'Limit order placed on {self.name} for {symbol} with side {side} and price {price} and quantity {quantity} with order id {order["orderId"]}')
            order = self._prep_order(order)
            if not order.oid:
                raise ValueError(f'Error while placing market order on {self.name}')
            if validate:
                order = self.get_order(symbol, order.oid)
            return order
        except:
            logger.error(f'Error placing limit order on {self.name}', exc_info=True)
            raise

    @authentication_required
    def get_order(self, symbol:'MarketSymbol|str', order:'Order|str') -> 'Order':
        from quantapi.models import Order
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        if isinstance(order, Order):
            _order_oid = order.oid
        else:
            _order_oid = order
        try:
            _order_payload = self.client.get_order(symbol=self._format_symbol(symbol.name), orderId=_order_oid)
            return self._prep_order(_order_payload)
        except:
            logger.error(f'Error while getting order on {self.name}', exc_info=True)
            raise

    @authentication_required
    def get_orders(self, symbol:'MarketSymbol|str') -> list['Order']:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        try:
            orders = self.client.get_all_orders(symbol=self._format_symbol(symbol.name))
            return [self._prep_order(order) for order in orders]
        except:
            logger.error(f'Error while getting order list on {self.name}', exc_info=True)
            raise

    @authentication_required
    def get_open_orders(self, symbol:'MarketSymbol|str') -> list['Order']:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        try:
            orders = self.client.get_open_orders(symbol=self._format_symbol(symbol.name))
            return [self._prep_order(order) for order in orders]
        except:
            logger.error(f'Error while getting open orders on {self.name}', exc_info=True)
            raise

    @authentication_required
    def cancel_order(self, symbol:'MarketSymbol|str', order:'Order|int') -> 'Order':
        from quantapi.models import Order
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        if isinstance(order, Order):
            _order_oid = order.oid
        else:
            _order_oid = order
        try:
            _order_payload = self.client.cancel_order(symbol=self._format_symbol(symbol.name), orderId=_order_oid)
            return self._prep_order(_order_payload)
        except Exception as e:
            if 'Unknown order sent' in str(e):
                logger.error(f'Order {_order_oid} not found on {self.name}')
            logger.error(f'Error while canceling order on {self.name}', exc_info=True)
            raise

    @authentication_required
    def cancel_all_orders(self, symbol:'MarketSymbol|str') -> list['Order']:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        try:
            if not self.client:
                raise ValueError('You must provide an API config to use this method')
            if symbol:
                orders = self.client._delete('openOrders', True, data={'symbol': self._format_symbol(symbol.name)})
            else:
                orders = self.client._delete('openOrders', True)
            return [self._prep_order(order) for order in orders]
        except:
            logger.error(f'Error while canceling all orders on {self.name}', exc_info=True)
            raise

    def get_full_orderbook(self, symbol:'MarketSymbol|str', limit=5000) -> dict:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        try:
            orderbook = self.client.get_order_book(symbol=self._format_symbol(symbol.name), limit=limit)
            return {
                'bids': [ { 'price': Decimal(item[0]), 'size': Decimal(item[1]), 'count': 1 } for item in orderbook['bids'] ],
                'asks': [ { 'price': Decimal(item[0]), 'size': Decimal(item[1]), 'count': 1 } for item in orderbook['asks'] ],
            }
        except:
            logger.error(f'Error while fetching orderbook for {symbol} on {self.name}', exc_info=True)
            return {}

    def init_orderbook_websocket(self, symbol:'MarketSymbol|str', callback:Callable, liveloop:'LiveLoop|None'=None, retries=30):
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        ws_uri = f'wss://stream.binance.com:9443/ws/{self._format_symbol(symbol.name).lower()}@depth@100ms'
        try:
            ws = connect(ws_uri)
            while not self.stop_websocket_stream and not (liveloop and liveloop.should_stop()):
                ws.pong()
                try:
                    data = json.loads(ws.recv(timeout=1))
                except TimeoutError:
                    continue
                orderbook = {
                    'bids': [ { 'price': Decimal(item[0]), 'size': Decimal(item[1]), 'count': 1 } for item in data['b'] ],
                    'asks': [ { 'price': Decimal(item[0]), 'size': Decimal(item[1]), 'count': 1 } for item in data['a'] ],
                }
                callback(orderbook)
        except:
            if retries < self.WS_MAX_RETRIES:
                retries += 1
                time.sleep(1)
                return self.init_orderbook_websocket(symbol, callback, liveloop, retries)
            msg = f'Cannot start websocket connection for orderbook for {symbol} on {self.name} (tried {retries} times).'
            logger.error(msg, exc_info=True)
            raise MarketAPIError(msg)

    @authentication_required
    def get_account(self):
        account = self.client.get_account()
        self.spot_trading_enabled = 'SPOT' in account.get('permissions', []) and account.get('canTrade')
        self.assets = { str(asset['asset']): float(asset['free']) for asset in account.get('balances', []) }
        self.capital = self.assets.get('USDT', 0)
        self.commission = {
            'buyer': float(account.get('buyerCommission', 0)),
            'seller': float(account.get('sellerCommission', 0)),
            'maker': float(account.get('makerCommission', 0)),
            'taker': float(account.get('takerCommission', 0)),
        }
        if not account.get('balances'):
            logger.error('`balances` key not found in account data, revise Binance interface')
        if not self.spot_trading_enabled:
            logger.error('Spot trading is not enabled on Binance account')

    @authentication_required
    def get_current_prices(self, save=True) -> dict:
        try:
            prices = { self._standardize_symbol(ticker['symbol']): float(ticker['price']) for ticker in self.client.get_all_tickers() if ticker['symbol'].endswith('USDT') and ticker['price'] }
            if self.market and self.market.prices != prices:
                self.market.prices = json.dumps(prices)
                if save:
                    self.market.save()
            return prices
        except:
            logger.error(f'Error while fetching current prices from {self.name}', exc_info=True)
            return {}

    @authentication_required
    def get_equity(self, save=True) -> float:
        prices = self.get_current_prices(save=False)
        if not prices:
            prices = json.loads(self.market.prices or '{}')
        equity = self.capital + sum([ self.assets.get(asset, 0) * prices.get(asset+'-USDT', 0) for asset in self.assets ])
        if self.account and self.account.equity != equity:
            self.account.equity = equity
            if save:
                self.account.save()
        return equity
