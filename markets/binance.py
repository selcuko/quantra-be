import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal, Optional

import pytz
import requests
from binance.client import Client

from logger import logger
from markets.helper import authentication_required, float_to_precision
from markets.interface import IMarket
from models import interval_to_minutes
from quantapi.models import Order, Symbol


class BinanceMarket(IMarket):
    name = 'BINANCE'

    def __init__(self, config=None):
        if config is None:
            config = {}
        self.authenticated = bool(config.get('API_KEY') and config.get('API_SECRET'))
        self.testnet = False
        self.spot_trading_enabled = False
        self.capital = 0
        self.assets = {}
        self.commission = {}
        try:
            if self.authenticated:
                self.testnet = config.get('TESTNET', False)
                self.client = Client(
                    api_key=config['API_KEY'],
                    api_secret=config['API_SECRET'],
                    testnet=self.testnet)
            else:
                self.client = Client()
        except:
            logger.fatal(f'Error while initializing {self.name}', exc_info=True)
            raise
        self.symbols = self.get_symbols()
        if self.authenticated:
            self.get_account()

    def __str__(self) -> str:
        return f'{self.name} (Authenticated: {self.authenticated})'

    def json(self) -> dict:
        return {
            'name': self.name,
            'authenticated': self.authenticated,
            'testnet': self.testnet,
            'spot_trading_enabled': self.spot_trading_enabled,
        }

    def _standardize_klines(self, klines:list[list]) -> list[list]:
        return [[ self._standardize_datetime(kline[0]),
                  float(kline[1]),
                  float(kline[2]),
                  float(kline[3]),
                  float(kline[4]),
                  float(kline[5]),
                ] for kline in klines ]

    def _standardize_symbol(self, symbol:dict) -> str:
        return f'{symbol["baseAsset"]}-{symbol["quoteAsset"]}'

    def _standardize_datetime(self, dtstr:str) -> datetime:
        return datetime.fromtimestamp(int(dtstr) // 1000, tz=pytz.UTC).replace(second=0, microsecond=0)

    def _format_symbol(self, symbol:str) -> str:
        assert '-' in symbol, f'Symbol must be in the format BASE-QUOTE (e.g. BTC-USDT), you provided: "{symbol}"'
        symbol = symbol.replace('-', '').upper()
        return symbol

    def _format_interval(self, interval) -> str:
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

    def _get_symbol_from_name(self, symbol_name:str) -> 'Symbol':
        try:
            _symbol = symbol_name
            return self.symbols[_symbol]
        except KeyError:
            logger.error(f'Symbol {symbol_name} is not present in {self.name}: {self.symbols.keys()}')
            raise ValueError(f'Symbol {symbol_name} is not present in {self.name}')

    @staticmethod
    def _prep_symbol(symbol:dict) -> 'Symbol':
        exc_symbol = Symbol(
                name = symbol['symbol'],
                base = symbol['baseAsset'],
                quote = symbol['quoteAsset'],
                base_precision = symbol['baseAssetPrecision'],
                quote_precision = symbol['quotePrecision'],
                spot_trading_enabled = symbol['isSpotTradingAllowed'],
                margin_trading_enabled = symbol['isMarginTradingAllowed'])
        return exc_symbol

    def _prep_order(self, order:dict, symbol:'Symbol') -> Order:
        order_time = order.get('time') or order.get('workingTime') or order.get('transactTime') or order.get('updateTime') or 0
        return Order(
            oid=order['orderId'],
            client_oid=order['clientOrderId'],
            order_type=order['type'].upper(),
            price=float(order['price']),
            timestamp=datetime.fromtimestamp(int(order_time // 1000), tz=pytz.UTC),
            deal_funds=float(order.get('cummulativeQuoteQty', 0)),
            deal_size=float(order.get('origQty', 0)),
            status=order['status'].upper(),
            funds=float(order.get('origQuoteOrderQty', 0)),
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
        except:
            logger.error(f'Error fetching klines for {symbol} from {self.name}', exc_info=True)
            if retry > 0:
                logger.warning(f'Retrying {retry} more times')
                time.sleep(1)
                return self._get_klines(symbol, interval, start, end, limit, retry-1)
            raise
        return self._standardize_klines(klines)

    def get_klines(self, symbol:str, interval:str, start:datetime, end:Optional[datetime]=None, limit=1000, retry=0) -> list[list]:
        if not symbol in self.symbols:
            raise ValueError(f'Symbol {symbol} is not present on {self.name}')
        try:
            return self._get_klines(symbol, interval, start, end, limit, retry=retry)
        except requests.exceptions.ConnectionError:
            return []

    def get_last_klines(self, symbol:str, interval:str, limit=100, retry=1, silent=True) -> list[list]:
        minutes = interval_to_minutes(interval)
        now = datetime.now(tz=pytz.UTC)
        start = now - timedelta(minutes=minutes*limit)
        klines = self.get_klines(symbol, interval, start, now, limit=limit*2)
        if klines == []:
            logger.warning(f'No klines found for {symbol} at {start} -> {now}')
            return []
        last_kline_dt = klines[-1][0]
        if (now - last_kline_dt) > timedelta(minutes=minutes*2):
            error = f'Last kline dt {last_kline_dt} does not match current time {now}, total klines: {len(klines)}, {start} -> {now}'
            logger.warning(error)
            if retry > 0:
                return self.get_last_klines(symbol, interval, limit, retry-1, silent)
            if not silent:
                raise ValueError(error)
        return klines

    def get_symbols(self) -> dict[str, 'Symbol']:
        return { self._standardize_symbol(symbol): self._prep_symbol(symbol) for symbol in self.client.get_exchange_info()['symbols']}

    @authentication_required
    def place_market_order(self, symbol:'Symbol|str', side:Literal['buy', 'sell'], funds:Optional[float]=None, quantity:Optional[float]=None, validate=True) -> Order:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        client_oid = uuid.uuid4().hex
        if (not funds and not quantity) or (funds and quantity):
            raise ValueError(f'You must provide either funds or quantity to place a market order on {self.name}')
        if funds and symbol.quote_precision:
            funds = float_to_precision(Decimal(funds), Decimal(symbol.quote_precision))
        if quantity and symbol.base_precision:
            quantity = float_to_precision(Decimal(quantity), Decimal(symbol.base_precision))
        _order_payload = self.client.order_market(
            side=side,
            symbol=symbol.name,
            quantity=quantity,
            quoteOrderQty=funds,
            newClientOrderId=client_oid)
        order = self._prep_order(_order_payload, symbol)
        logger.info(f'Market order placed on {self.name} for {symbol} with side {side} and funds {funds} and quantity {quantity} with order id {_order_payload["orderId"]}')
        if not order.oid:
            raise ValueError(f'Error while placing market order on {self.name}')
        if validate:
            order = self.get_order(symbol, order.oid)
        return order

    @authentication_required
    def place_limit_order(self, symbol:Symbol|str, side:Literal['buy', 'sell'], price:float, quantity:float, validate=True) -> Order:
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
                symbol=symbol.name,
                price=price,
                quantity=quantity,
                newClientOrderId=client_oid)
            logger.info(f'Limit order placed on {self.name} for {symbol} with side {side} and price {price} and quantity {quantity} with order id {order["orderId"]}')
            order = self._prep_order(order, symbol)
            if not order.oid:
                raise ValueError(f'Error while placing market order on {self.name}')
            if validate:
                order = self.get_order(order.signal.session.symbol, order.oid)
            return order
        except:
            logger.error(f'Error placing limit order on {self.name}', exc_info=True)
            raise

    @authentication_required
    def get_order(self, symbol:Symbol|str, order:Order|str) -> Order:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        if isinstance(order, Order):
            _order_oid = order.oid
        else:
            _order_oid = order
        try:
            _order_payload = self.client.get_order(symbol=symbol.name, orderId=_order_oid)
            return self._prep_order(_order_payload, symbol)
        except:
            logger.error(f'Error while getting order on {self.name}', exc_info=True)
            raise

    @authentication_required
    def get_orders(self, symbol:Symbol|str) -> list[Order]:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        try:
            orders = self.client.get_all_orders(symbol=symbol.name)
            return [self._prep_order(order, symbol) for order in orders]
        except:
            logger.error(f'Error while getting order list on {self.name}', exc_info=True)
            raise

    @authentication_required
    def get_open_orders(self, symbol:'Symbol|str') -> list['Order']:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        try:
            orders = self.client.get_open_orders(symbol=symbol.name)
            return [self._prep_order(order, symbol) for order in orders]
        except:
            logger.error(f'Error while getting open orders on {self.name}', exc_info=True)
            raise

    @authentication_required
    def cancel_order(self, symbol:Symbol|str, order:Order|int) -> Order:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        if isinstance(order, Order):
            _order_oid = order.oid
        else:
            _order_oid = order
        try:
            _order_payload = self.client.cancel_order(symbol=symbol.name, orderId=_order_oid)
            return self._prep_order(_order_payload, symbol)
        except Exception as e:
            if 'Unknown order sent' in str(e):
                logger.error(f'Order {_order_oid} not found on {self.name}')
            logger.error(f'Error while canceling order on {self.name}', exc_info=True)
            raise

    @authentication_required
    def cancel_all_orders(self, symbol:Symbol|str) -> list[Order]:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        try:
            if not self.client:
                raise ValueError('You must provide an API config to use this method')
            if symbol:
                orders = self.client._delete('openOrders', True, data={'symbol': self._format_symbol(symbol.name)})
            else:
                orders = self.client._delete('openOrders', True)
            return [self._prep_order(order, symbol) for order in orders]
        except:
            logger.error(f'Error while canceling all orders on {self.name}', exc_info=True)
            raise

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
