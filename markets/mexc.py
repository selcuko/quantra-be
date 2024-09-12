import hashlib
import hmac
import json
from threading import Event
import time
import typing
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable, Literal, Optional
from urllib.parse import urlencode

import pytz
import requests
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK
from websockets.sync.client import ClientConnection, connect

import incident
from logger import logger
from markets import IMarket
from markets.errors import InsufficientBalance, InvalidUsage, KlineFetchFailed, MarketAPIError, RejectedOrder
from markets.helper import authentication_required
from match import MatchEngine
from models import interval_to_minutes

if typing.TYPE_CHECKING:
    from loops.liveloop import LiveLoop
    from quantapi.models import MarketAccount, MarketSymbol, Order, Market


class MEXCMarket(IMarket):
    name = 'MEXC'

    def __init__(self, config: dict, account: 'MarketAccount|None', market:'Market|None'=None) -> None:
        self.authenticated = False
        self.session = requests.Session()
        self.url = 'https://api.mexc.com'
        self.furl = 'https://contract.mexc.com'
        if config:
            self.authenticated = True
            self.api_secret = config['API_SECRET']
            self.access_key = config['ACCESS_KEY']
            self.session.headers.update({
                'X-MEXC-APIKEY': config['ACCESS_KEY'],
            })
        self.account = account
        self.market = account.market if account else market  # type: ignore

        self.symbols = {}
        self.capital = 0
        self.assets = {}
        self.commission = {}

        try:
            self.get_symbols()
            self.get_account()
        except requests.ConnectionError as exc:
            incident.Market.APIUnavailable(self.name, exc)
            return

        self.spot_trading_enabled = False
        self.margin_trading_enabled = False
        self.stop_websocket_stream = False

    def verify_key(self, response):
        return 'api key info invalid' not in response.get('msg', '').lower()

    def format_ws_candle(self, candle):
        return {
                'time': datetime.fromtimestamp(candle['t'], pytz.UTC).replace(second=0, microsecond=0),
                'start': datetime.fromtimestamp(candle['t'], pytz.UTC).replace(second=0, microsecond=0),
                'end': datetime.fromtimestamp(candle['T'], pytz.UTC).replace(second=0, microsecond=0),
                'volume': float(candle['a']),
                'close': float(candle['c']),
                'high': float(candle['h']),
                'low': float(candle['l']),
                'open': float(candle['o']),
                'quantity': float(candle['v']),
            }

    @staticmethod
    def interval_to_ws(interval:str):
        return {
            '1 min': 'Min1',
            '3 min': 'Min3',
            '5 min': 'Min5',
            '15 min': 'Min15',
            '30 min': 'Min30',
            '1 hour': 'Min60',
            '4 hour': 'Hour4',
            '8 hour': 'Hour8',
            '1 day': 'Day1',
            '1 week': 'Week1',
            '1 month': 'Month1'
        }[interval]

    def format_match(self, data):
        return {
            'time': datetime.fromtimestamp(int(data['t']) / 1000, pytz.UTC).replace(second=0, microsecond=0),
            'size': float(data['v']),
            'price': float(data['p']),
            'maker': True if data['S'] == 1 else False,
        }

    def get_match_engine_ws(self, symbol:str) -> ClientConnection:
        ws_uri = 'wss://wbs.mexc.com/ws'
        ws = connect(ws_uri)
        topic = f'spot@public.deals.v3.api@{self._format_symbol(symbol)}'
        sub = {
            'method': 'SUBSCRIPTION',
            'params': [topic]
        }
        ws.send(json.dumps(sub))
        ack = json.loads(ws.recv())
        if not ack.get('msg') == topic:
            raise Exception(f'Error while subscribing to {topic}: {ack}')
        return ws

    def init_match_engine(self, symbol:str, interval:str, callback:Callable, stop_event: Event, raw_callback:Optional[Callable]=None, ticker_callback:Optional[Callable]=None):
        ws = self.get_match_engine_ws(symbol)
        last_ping = datetime.now()
        me = MatchEngine(interval, callback, ticker_callback)
        retries = 0
        while not stop_event.is_set():
            if (datetime.now() - last_ping).seconds > 30:
                ws.send('{"method": "PING"}')
                last_ping = datetime.now()
            try:
                response = json.loads(ws.recv(timeout=10))
                retries = 0
            except TimeoutError:
                continue
            except (ConnectionClosed, ConnectionClosedOK):
                ws = self.get_match_engine_ws(symbol)
                continue
            except:
                if retries > self.WS_MAX_RETRIES:
                    logger.error(f'Error while initializing match engine for {symbol} on {self.name}', exc_info=True)
                    raise
                retries += 1
                ws = self.get_match_engine_ws(symbol)
                continue
            if response.get('msg') == 'PONG':
                continue
            if raw_callback:
                raw_callback(response)
            deals = response['d']['deals']
            for deal in deals:
                me.on_match(self.format_match(deal))

    def init_websocket(self, symbol:str, interval:str, callback:Callable, liveloop:'LiveLoop'):
        ws_uri = 'wss://wbs.mexc.com/ws'
        ws = connect(ws_uri)
        topic = f'spot@public.kline.v3.api@{self._format_symbol(symbol)}@{self.interval_to_ws(interval)}'
        sub = {
            'method': 'SUBSCRIPTION',
            'params': [topic]
        }
        ws.send(json.dumps(sub))
        ack = json.loads(ws.recv())
        if not ack.get('msg') == topic:
            raise Exception(f'Error while subscribing to {topic}: {ack}')
        last_ping = datetime.now()
        last_kline = None
        while not self.stop_websocket_stream and not liveloop.should_stop():
            if (datetime.now() - last_ping).seconds > 30:
                ws.send('{"method": "PING"}')
                last_ping = datetime.now()
            try:
                response = json.loads(ws.recv(timeout=10))
            except TimeoutError:
                continue
            if response.get('msg') == 'PONG':
                continue
            candle = self.format_ws_candle(response['d']['k'])
            if last_kline and candle['end'] > last_kline:
                callback(candle)
                last_kline = candle['end']
            if not last_kline:
                last_kline = candle['end']

    def get_full_orderbook(self, symbol:'MarketSymbol|str', limit=500):
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        try:
            if symbol.contract_type == symbol.ContractType.SPOT:
                uri = f'{self.url}/api/v3/depth?symbol={self._format_symbol(symbol.name)}&limit={limit}' 
            elif symbol.contract_type == symbol.ContractType.FUTURES:
                uri = f'{self.furl}/api/v1/contract/depth/{symbol.name.replace("-","_")}'
            else:
                raise ValueError(f'Unknown contract type for symbol {symbol.name}')
            response = requests.get(uri)
            orderbook = response.json()
        except:
            logger.error(f'Error while fetching orderbook for {self.name}', exc_info=True)
            raise
        if symbol.contract_type == symbol.ContractType.FUTURES:
            orderbook = orderbook['data']
        return self.format_orderbook_snapshot(orderbook)

    def format_orderbook_snapshot(self, orderbook):
        return {
            'bids': [ { 'price': Decimal(bid[0]), 'size': Decimal(bid[1]), 'count': 1 } for bid in orderbook['bids'] ],
            'asks': [ { 'price': Decimal(ask[0]), 'size': Decimal(ask[1]), 'count': 1 } for ask in orderbook['asks'] ],
        }

    def format_orderbook_update(self, update):
        return {
            'bids': [ { 'price': Decimal(bid['p']), 'size': Decimal(bid['v']), 'count': 1 } for bid in update.get('bids', []) ],
            'asks': [ { 'price': Decimal(ask['p']), 'size': Decimal(ask['v']), 'count': 1 } for ask in update.get('asks', []) ],
        }

    def init_orderbook_websocket(self, symbol:'MarketSymbol|str', callback:Callable):
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        topic = f'spot@public.increase.depth.v3.api@{self._format_symbol(symbol.name)}'
        if  symbol.contract_type == symbol.ContractType.SPOT:
            ws_uri = 'wss://wbs.mexc.com/ws'
            sub = {
                'method': 'SUBSCRIPTION',
                'params': [topic]
            }
        elif symbol.contract_type == symbol.ContractType.FUTURES:
            ws_uri = 'wss://contract.mexc.com/edge'
            sub = {
                "method": "sub.depth",
                "param": {
                    "symbol": symbol.name.replace('-','_')
                }
            }
        else:
            raise ValueError(f'Unknown contract type for symbol {symbol.name}')
        try:
            ws = connect(ws_uri)
        except TimeoutError:
            time.sleep(5)
            return self.init_orderbook_websocket(symbol, callback)

        ws.send(json.dumps(sub))
        ack = json.loads(ws.recv())
        if symbol.contract_type == symbol.ContractType.SPOT and not ack.get('msg') == topic and not ack.get('c') == topic:
            raise Exception(f'Error while subscribing to {topic}: {ack}')
        last_ping = datetime.now()
        while not self.stop_websocket_stream:
            try:
                if (datetime.now() - last_ping).seconds > 30:
                    ws.send('{"method": "PING"}')
                    last_ping = datetime.now()
                response = json.loads(ws.recv(timeout=10))
            except TimeoutError:
                continue
            except ConnectionClosed:
                return self.init_orderbook_websocket(symbol, callback)
            if response.get('msg') == 'PONG':
                continue
            if symbol.contract_type == symbol.ContractType.SPOT:
                response = response['d']
                orderbook = self.format_orderbook_update(response)
            elif symbol.contract_type == symbol.ContractType.FUTURES:
                response = response['data']
                orderbook = self.format_orderbook_snapshot(response)
            callback(orderbook)
        ws.close()

    def has_symbol(self, symbol: str) -> bool:
        if not self.symbols:
            self.get_symbols()
        return symbol in self.symbols

    def _standardize_klines(self, klines):
        klines = [[
            self._standardize_datetime(kline[0]),
            float(kline[1]),
            float(kline[2]),
            float(kline[3]),
            float(kline[4]),
            float(kline[5]),
        ] for kline in klines ]
        return klines

    @staticmethod
    def _standardize_symbol(symbol):
        return symbol.replace('USDT', '-USDT')

    @staticmethod
    def _format_symbol(symbol):
        assert '-' in symbol, f'Symbol must be in the format BASE-QUOTE, you provided: {symbol}'
        return symbol.replace('-', '').upper()

    @staticmethod
    def _format_interval(interval):
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
            '1 week': '1W',
            '1 month': '1M',
        }[interval]

    @staticmethod
    def _format_datetime(dt):
        return str(int(dt.timestamp()*1000))

    @staticmethod
    def _standardize_datetime(dt):
        return datetime.fromtimestamp(int(dt) // 1000, tz=pytz.UTC).replace(second=0, microsecond=0)

    def sign(self, query_string) -> str:
        signature = hmac.new(self.api_secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        return query_string + '&signature=' + signature

    def _prep_payload(self, payload=None) -> str:
        if not payload:
            payload = {}
        payload = { k:v for k,v in payload.items() if v is not None }
        payload['timestamp'] = self._format_datetime(datetime.now(tz=pytz.UTC))
        payload = urlencode(payload, doseq=True).replace('+', '%20')
        payload = self.sign(payload)
        return payload

    def get_klines(self, symbol, interval, start=None, end=None, limit=1000, retry=1):
        return self._get_klines(symbol, interval, start, end, limit, retry=retry)

    def get_account(self, save=True):
        if not self.authenticated or not self.account:
            return
        uri = f'{self.url}/api/v3/account'
        request_query = self._prep_payload()
        response = self.session.get(uri, params=request_query)
        if not response.ok:
            if not self.verify_key(response.json()):
                raise incident.Market.KeyExpired(self.account) 
            raise MarketAPIError(f'{self.name} API error: {response.text}')
        account_payload = response.json()
        self.spot_trading_enabled = 'SPOT' in account_payload.get('permissions', [])
        self.margin_trading_enabled = 'MARGIN' in account_payload.get('permissions', [])

        for asset in account_payload['balances']:
            self.assets[asset['asset']] = float(asset['free'])
        self.capital = self.assets.get('USDT', 0)

        self.account.capital = self.capital
        self.account.assets = json.dumps(self.assets)
        if save:
            self.account.save()

    def _get_klines(self, symbol, interval, start=None, end=None, limit=1000, retry=3):
        if not isinstance(symbol, str):
            symbol = symbol.name
        if not end and not start:
            raise InvalidUsage('Either start or end must be provided')
        if limit > 1000:
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
                raise InvalidUsage(f'We can get a maximum of 1000 klines per request (limit={limit}), your timerange is too wide ({candles_in_timerange} candles), please reduce the timerange or increase the interval')
        try:
            uri = f'{self.url}/api/v3/klines?symbol={self._format_symbol(symbol)}&interval={self._format_interval(interval)}&limit={limit}&startTime={self._format_datetime(start)}&endTime={self._format_datetime(end)}'
            response = requests.get(uri)
            if not response.ok:
                raise ValueError(f'Error while fetching klines for {self.name}: {response.text}')
            kline_data = response.json()
        except Exception as e:
            incident.Market.CandleFetchFailed(self.name, e)
            if retry > 0:
                time.sleep(1)
                return self._get_klines(symbol, interval, start, end, limit, retry-1)
            raise incident.Market.CandleFetchFailed(self.name, e)
        if not kline_data or not isinstance(kline_data, list) or not isinstance(kline_data[0], list):
            return []
        return self._standardize_klines(kline_data)

    def _prep_symbol(self, symbol):
        from quantapi.models import MarketSymbol
        return MarketSymbol(
            market=self.market,
            name=self._standardize_symbol(symbol['symbol']),
            base=symbol['baseAsset'],
            quote=symbol['quoteAsset'],
            base_precision=symbol['baseSizePrecision'][:10],      # MEXC specific (they use ints)
            quote_precision=symbol['quoteAmountPrecision'][:10],  # MEXC specific (they use ints)
            spot_trading_enabled=symbol['isSpotTradingAllowed'],
            margin_trading_enabled=symbol['isMarginTradingAllowed'],
            details=json.dumps(symbol),
        )

    def get_symbols(self):
        from quantapi.models import MarketSymbol
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
        MarketSymbol.objects.bulk_create(self.symbols.values(), update_conflicts=True, update_fields=[
                'spot_trading_enabled', 
                'margin_trading_enabled', 
                'details',
                'base_precision',
                'quote_precision',
            ], unique_fields=['name', 'market', 'contract_type'])
        return self.symbols

    def get_last_klines(self, symbol:'MarketSymbol|str', interval:str, limit=100, retry=1, silent=True):
        minutes = interval_to_minutes(interval)
        now = datetime.now(tz=pytz.UTC)
        start = now - timedelta(minutes=minutes*limit)
        klines = self.get_klines(symbol, interval, start, now, limit, retry)
        if not klines:
            return []
        last_kline_dt = klines[-1][0]
        if (now - last_kline_dt) > timedelta(minutes=minutes*2):
            error = f'Last kline dt {last_kline_dt} does not match current time {now}, total klines: {len(klines)}, {start} -> {now}'
            logger.warning(error)
            raise KlineFetchFailed(error)
        return klines

    def _get_symbol_from_name(self, name):
        if name not in self.symbols:
            raise ValueError(f'Symbol {name} is not available on {self.name}')
        return self.symbols[name]

    def _prep_order(self, order):
        from quantapi.models import Order
        order_time = order.get('time') or order.get('transactTime') or order.get('timestamp') or 0
        return Order(
            oid=order.get('orderId'),
            client_oid=order.get('clientOrderId'),
            order_type=order.get('type', 'MARKET'),
            price=float(order.get('price', 0)),
            market_timestamp=self._standardize_datetime(order_time),
            deal_funds=float(order.get('origQuoteOrderQty', 0)),
            deal_size=float(order.get('executedQty', 0)) or float(order.get('origQty', 0)),
            funds=float(order.get('origQuoteOrderQty', 0)),
            status=order.get('status', 'FILLED' if order.get('orderId') else 'REJECTED'),
            details=json.dumps(order),
            account=self.account,
        )

    @authentication_required
    def place_market_order(self, symbol: 'MarketSymbol|str', side: Literal['buy', 'sell'], funds: str | None = None, quantity: str | None = None, validate=True) -> 'Order':
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        client_oid = uuid.uuid4().hex
        if not (funds or quantity) or (funds and quantity):
            raise ValueError('Either funds or quantity must be provided')
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
            order = self._prep_order(order_data)
            if not order.oid:
                if order_data.get('msg') == 'Oversold' and side == 'sell':
                    raise InsufficientBalance(f'Not enough balance to place order on {self.name} (we have {self.assets.get(symbol.base, 0)} {symbol.base} but tried to sell {quantity} {symbol.base}): {order_data}')
                elif order_data.get('msg') == 'Insufficient position' and side == 'buy':
                    raise InsufficientBalance(f'Not enough balance to place order on {self.name} (we have {self.assets.get(symbol.quote, 0)} {symbol.quote} but tried to buy with {funds} {symbol.quote}): {order_data}')
                raise RejectedOrder(f'Error while placing order on {self.name}: {order_data}\nOrder query: {order_query}')
            order.request = json.dumps({
                'side': side,
                'symbol': symbol.name,
                'funds': funds,
                'quantity': quantity,
                'client_oid': client_oid,
            })
            return order
        except Exception as e:
            if 'insufficient' in str(e).lower():
                raise InsufficientBalance(f'Not enough balance to place order on {self.name}: {e}')
            logger.error(f'Error while placing order on {self.name}', exc_info=True)
            raise

    @authentication_required
    def get_order(self, symbol:'MarketSymbol|str', order:'Order|str') -> 'Order':
        from quantapi.models import Order
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        if isinstance(order, Order):
            order_id = order.oid
        else:
            order_id = order
        try:
            order_query = self._prep_payload({ 
                                                    'symbol': self._format_symbol(symbol.name),
                                                    'orderId': order_id,
                                                    'timestamp': str(int(time.time()*1000)),
                                                })
            
            uri = f'{self.url}/api/v3/order'
            response = self.session.request('GET', uri, params=order_query )
            order_data = response.json()
            if order_data.get('msg') == 'Order does not exist':
                raise Exception(f'Order {order_id} does not exist on {self.name}')
            order = self._prep_order(order_data)
            return order
        except:
            logger.error(f'Error while getting order on {self.name}', exc_info=True)
            raise

    @authentication_required
    def get_current_prices(self, save=True) -> dict:
        uri = f'{self.url}/api/v3/ticker/price'
        response = self.session.get(uri)
        if not response.ok:
            raise Exception(f'Error while fetching current prices for {self.name}: {response.text}')
        try:
            all_tickers = response.json()
        except:
            return {}
        
        prices = { self._standardize_symbol(ticker['symbol']): float(ticker['price']) for ticker in all_tickers if ticker['symbol'].endswith('USDT') and ticker['price'] }
        if self.market:
            self.market.prices = json.dumps(prices)
            if save:
                self.market.save()
        return prices

    @authentication_required
    def get_equity(self, save=True):
        prices = self.get_current_prices(save=False)
        equity = self.capital + sum([ self.assets.get(asset, 0) * prices.get(asset+'-USDT', 0) for asset in self.assets ])
        if self.account:
            self.account.equity = equity
            if save:
                self.account.save()
        return equity
