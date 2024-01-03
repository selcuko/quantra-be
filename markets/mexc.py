import hashlib
import hmac
import json
from pprint import pprint


import time
from datetime import datetime, timedelta
from typing import Literal, Optional
from urllib.parse import urlencode
import uuid

import pytz
import requests

from logger import logger
from markets import IMarket
from markets.errors import InsufficientBalance, RejectedOrder
from markets.helper import authentication_required, float_to_precision
from models import interval_to_minutes
from quantapi.models import Market, Order, Symbol


class MEXCMarket(IMarket):
    name = 'MEXC'
    def __init__(self, config=None, market=None) -> None:
        self.authenticated = False
        self.session = requests.Session()
        self.url = 'https://api.mexc.com'
        if config:
            self.authenticated = True
            self.api_secret = config['API_SECRET']
            self.access_key = config['ACCESS_KEY']
            self.session.headers.update({
                'X-MEXC-APIKEY': config['ACCESS_KEY'],
            })

        self.market = market
        if not self.market:
            self.market = Market.objects.filter(exchange_name=self.name).first()

        self.symbols = {}
        self.capital = 0
        self.assets = {}
        self.commission = {}

        self.get_symbols()
        self.get_account()

    def has_symbol(self, symbol: str) -> bool:
        if not self.symbols:
            self.get_symbols()
        return symbol in self.symbols

    def _standardize_klines(self, klines):
        klines = [[ self._standardize_datetime(kline[0]),
                  float(kline[1]),
                  float(kline[2]),
                  float(kline[3]),
                  float(kline[4]),
                  float(kline[5]),
                ] for kline in klines ]
        return klines
    
    def _standardize_symbol(self, symbol):
        return symbol.replace('USDT', '-USDT')
    
    def _format_symbol(self, symbol):
        assert '-' in symbol, f'Symbol must be in the format BASE-QUOTE, you provided: {symbol}'
        return symbol.replace('-', '').upper()
    
    def _format_interval(self, interval):
        return {
            '1 min': '1m',
            '3 min': '3m',
            '5 min': '5m',
            '15 min': '15m',
            '30 min': '30m',
            '1 hour': '1h',
            '2 hour': '2h',
            '4 hour': '4h',
            '6 hour': '6h',
            '8 hour': '8h',
            '12 hour': '12h',
            '1 day': '1d',
            '3 day': '3d',
            '1 week': '1w',
            '1 month': '1M',
        }[interval]
    
    def _format_datetime(self, dt):
        return str(int(dt.timestamp()*1000))

    def _standardize_datetime(self, dt):
        return datetime.fromtimestamp(int(dt) // 1000, tz=pytz.UTC).replace(second=0, microsecond=0)

    def sign(self, query_string) -> str:
        signature = hmac.new(self.api_secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        return query_string + '&signature=' + signature

    def _prep_payload(self, payload={}) -> str:
        payload = { k:v for k,v in payload.items() if v is not None }
        payload['timestamp'] = self._format_datetime(datetime.now(tz=pytz.UTC))
        payload = urlencode(payload, doseq=True).replace('+', '%20')
        payload = self.sign(payload)
        return payload

    def get_klines(self, symbol, interval, start=None, end=None, limit=1000):
        return self._get_klines(symbol, interval, start, end, limit)

    def get_account(self):
        uri = f'{self.url}/api/v3/account'
        try:
            request_query = self._prep_payload()
            response = self.session.get(uri, params=request_query)
            account_payload = response.json()
            self.spot_trading_enabled = 'SPOT' in account_payload.get('permissions', [])
            self.margin_trading_enabled = 'MARGIN' in account_payload.get('permissions', [])
            
            for asset in account_payload['balances']:
                self.assets[asset['asset']] = float(asset['free'])
            self.capital = self.assets.get('USDT', 0)

        except:
            logger.error(f'Error while fetching account data for {self.name}', exc_info=True)
            raise

    def _get_klines(self, symbol, interval, start=None, end=None, limit=1000, retry=3):
        if not end and not start:
            raise ValueError('Either start or end must be provided')
        if not limit or limit > 1000:
            logger.warning(f'MEXC only allows a maximum of 1000 klines per request, you requested {limit}')
            limit = 1000
        calculated_timerange = timedelta(minutes=interval_to_minutes(interval) * limit)
        if not start and end:
            start = end - calculated_timerange
        elif not end and start:
            end = start + calculated_timerange
        elif end and start:
            if end - start > calculated_timerange:
                # calculate how many candles are in the timerange
                candles_in_timerange = (end - start) // timedelta(minutes=interval_to_minutes(interval))
                raise ValueError(f'We can get a maximum of 1000 klines per request (limit={limit}), your timerange is too wide ({candles_in_timerange} candles), please reduce the timerange or increase the interval')
        try:
            uri = f'{self.url}/api/v3/klines?symbol={self._format_symbol(symbol)}&interval={self._format_interval(interval)}&limit={limit}&startTime={self._format_datetime(start)}&endTime={self._format_datetime(end)}'
            response = requests.get(uri)
            response.raise_for_status()
            kline_data = response.json()
        except:
            logger.error(f'Error while fetching klines for {self.name}', exc_info=True)
            if retry > 0:
                logger.warning(f'Retrying {retry} more times')
                time.sleep(1)
                return self._get_klines(symbol, interval, start, end, limit, retry-1)
            raise
        if not kline_data or not isinstance(kline_data, list) or not isinstance(kline_data[0], list):
            return []
        return self._standardize_klines(kline_data)

    def _prep_symbol(self, symbol):
        from quantapi.models import Symbol
        return Symbol(
            market = self.market,
            name = self._standardize_symbol(symbol['symbol']),
            base = symbol['baseAsset'],
            quote = symbol['quoteAsset'],
            base_precision = symbol['baseSizePrecision'][:10],  # MEXC specific (they use ints)
            quote_precision = symbol['quoteAmountPrecision'][:10], # MEXC specific (they use ints)
            spot_trading_enabled = symbol['isSpotTradingAllowed'],
            margin_trading_enabled = symbol['isMarginTradingAllowed'],
            details=json.dumps(symbol),
        )

    def get_symbols(self):
        try:
            uri = f'{self.url}/api/v3/exchangeInfo'
            response = requests.get(uri)
            response.raise_for_status()
            symbols = response.json()['symbols']
        except:
            logger.error(f'Error while fetching symbols for {self.name}', exc_info=True)
            raise
        self.symbols = { self._standardize_symbol(symbol['symbol']): self._prep_symbol(symbol) for symbol in symbols if symbol['quoteAsset'] == 'USDT' }
        self.symbols = { key: value for key, value in self.symbols.items() if value.quote == 'USDT'}
        Symbol.objects.bulk_create(self.symbols.values(), ignore_conflicts=True)
        return self.symbols

    def get_last_klines(self, symbol, interval, limit=100):
        minutes = interval_to_minutes(interval)
        now = datetime.now(tz=pytz.UTC)
        start = now - timedelta(minutes=minutes*limit)
        klines = self.get_klines(symbol, interval, start, now)
        if not klines:
            return []
        last_kline_dt = klines[-1][0]
        if (now - last_kline_dt) > timedelta(minutes=minutes):
            error = f'Last kline dt {last_kline_dt} does not match current time {now}, total klines: {len(klines)}, {start} -> {now}'
            logger.warning(error)
            raise Exception(error)
        return klines
    
    def _get_symbol_from_name(self, name):
        if name not in self.symbols:
            raise ValueError(f'Symbol {name} is not available on {self.name}')
        return self.symbols[name]

    def _prep_order(self, order, symbol):
        order_time = order.get('time') or order.get('transactTime') or order.get('timestamp') or 0
        return Order(
            oid = order.get('orderId'),
            client_oid = order.get('clientOrderId'),
            order_type = order.get('type', 'MARKET'),
            price = order.get('price'),
            timestamp = self._standardize_datetime(order_time),
            deal_funds = float(order.get('origQuoteOrderQty', 0)),
            deal_size = float(order.get('executedQty', 0)),
            funds = float(order.get('origQuoteOrderQty', 0)),
            status = order.get('status', 'NOT_FOUND'),
            details=json.dumps(order),        
        )

    @authentication_required
    def place_market_order(self, symbol: Symbol | str, side: Literal['buy', 'sell'], funds: float | None = None, quantity: float | None = None, validate=True) -> Order:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        client_oid = uuid.uuid4().hex
        if not (funds or quantity) or (funds and quantity):
            raise ValueError('Either funds or quantity must be provided')
        if funds and symbol.quote_precision:
            funds = float_to_precision(funds, symbol.quote_precision)
        if quantity and symbol.base_precision:
            quantity = float_to_precision(quantity, symbol.base_precision)
        try:
            uri = f'{self.url}/api/v3/order'
            order_query = self._prep_payload({ 
                                    'symbol': self._format_symbol(symbol.name),
                                    'side': side.upper(),
                                    'type': 'MARKET',
                                    'quantity':quantity,
                                    'quoteOrderQty':funds,
                                    'newClientOrderId':client_oid,
                                    'timestamp': str(int(time.time()*1000))
                                })

            response = self.session.request('POST', uri, params=order_query )
            order_data = response.json()
            order = self._prep_order(order_data, symbol)
            if not order.oid:
                if order_data.get('msg') == 'Oversold' and side == 'sell':
                    raise InsufficientBalance(f'Not enough balance to place order on {self.name} (we have {self.assets.get(symbol.base, 0)} {symbol.base} but tried to sell {quantity} {symbol.base}): {order_data}')
                elif order_data.get('msg') == 'Insufficient position' and side == 'buy':
                    raise InsufficientBalance(f'Not enough balance to place order on {self.name} (we have {self.assets.get(symbol.quote, 0)} {symbol.quote} but tried to buy with {funds} {symbol.quote}): {order_data}')
                raise RejectedOrder(f'Error while placing order on {self.name}: {order_data}\nOrder query: {order_query}')
            if validate:
                MAX_TRY = 10
                tries = 0
                while order.status not in ['FILLED', 'CANCELED', 'EXPIRED', 'REJECTED'] and tries < MAX_TRY or tries == 0:
                    time.sleep(1)
                    tries += 1
                    order = self.get_order(symbol, order)
                if order.status not in ['FILLED', 'CANCELED', 'EXPIRED', 'REJECTED']:
                    raise Exception(f'Order {order.oid} on {self.name} is still {order.status} after {MAX_TRY} tries')
            return order
        except:
            logger.error(f'Error while placing order on {self.name}', exc_info=True)
            raise

    @authentication_required
    def get_order(self, symbol:Symbol|str, order:Order|str):
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        if isinstance(order, Order):
            order = order.oid
        try:
            order_query = self._prep_payload({ 
                                                    'symbol': self._format_symbol(symbol.name),
                                                    'orderId': order,
                                                    'timestamp': str(int(time.time()*1000)),
                                                })
            
            uri = f'{self.url}/api/v3/order'
            response = self.session.request('GET', uri, params=order_query )
            order_data = response.json()
            if order_data.get('msg') == 'Order does not exist':
                return None
            order = self._prep_order(order_data, symbol)
            return order
        except:
            logger.error(f'Error while getting order on {self.name}', exc_info=True)
            raise
