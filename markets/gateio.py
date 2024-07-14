from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import hmac
import json
import time
import traceback
import requests
from logger import logger
from markets.errors import InsufficientBalance, KlineFetchFailed, MarketAPIError, MarketAPIUnrecognizedResponse, OrderPlacementError, OrderPostProcessingError, RejectedOrder
from markets.interface import IMarket
from logger import logger

from django.utils import timezone
import typing
from websockets.sync.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK
from match import MatchEngine
from models import interval_to_minutes
if typing.TYPE_CHECKING:
    from quantapi.models import MarketAccount, MarketSymbol, Order
    from loops import LiveLoop


class GateIOMarket(IMarket):
    name = 'Gate.io'

    def __init__(self, config: dict, account: 'MarketAccount'):
        self.url = 'https://api.gateio.ws'
        self.api_key = config['API_KEY']
        self.api_secret = config['API_SECRET']
        self.recv_window = 60000
        self.session = requests.Session()
        self.session.headers.update({
            'KEY': config['API_KEY'],
            'Content-Type': 'application/json'
        })

        self.account = account
        self.market = self.account.market
        self.spot_trading_enabled = True
        self.capital = 0
        self.symbols = {}
        self.assets = {}
        self.prices = {}
        self.authenticated = True
        self.stop_websocket_stream = False

        self.get_account()
        self.get_symbols()

    def sign(self, payload:dict, path:str, method:str='GET') -> str:
        if not payload:
            payload = {}
        now = self.format_timestamp(timezone.now())
        if method == 'GET':
            query = '&'.join([ f'{k}={v}' for k, v in payload.items() ])
            body  = hashlib.sha512(''.encode('utf-8')).hexdigest()
        else:
            query = ''
            body = hashlib.sha512(json.dumps(payload).encode('utf-8')).hexdigest()
        presign = f'{method}\n{path}\n{query}\n{body}\n{now}'
        hash = hmac.new(bytes(self.api_secret, "utf-8"), presign.encode("utf-8"), hashlib.sha512)
        signature = hash.hexdigest()
        self.session.headers['Timestamp'] = str(now)
        self.session.headers['SIGN'] = signature
        return query

    def get_account(self, save=True):
        path = '/api/v4/spot/accounts'
        url = f'{self.url}{path}'
        self.sign({}, path)
        response = self.session.get(url)
        data = response.json()
        if not response.ok:
            logger.error(f'Failed to fetch account data: {data}', extra={'market': self.name, 'type': 'MARKET'})
            raise MarketAPIError(f'Failed to fetch account data: {data}')
        for symbol in data:
            self.assets[symbol['currency']] = float(symbol['available'])
        self.capital = self.assets.get('USDT', 0)
        if self.account:
            self.account.capital = self.capital
            self.account.assets = json.dumps(self.assets)
            if save:
                self.account.save()

    def get_symbols(self):
        path = '/api/v4/spot/currency_pairs'
        url = f'{self.url}{path}'
        self.sign({}, path)
        response = self.session.get(url)
        data = response.json()
        self.symbols = { self.standardize_symbol(symbol['id']): self.prep_symbol(symbol) for symbol in data if symbol['id'].endswith('USDT') }
        if self.market:
            from quantapi.models import MarketSymbol
            MarketSymbol.objects.bulk_create(self.symbols.values(), update_conflicts=True, update_fields=[
                'spot_trading_enabled', 
                'margin_trading_enabled', 
                'details',
                'base_precision',
                'quote_precision',
            ], unique_fields=['name', 'market'], batch_size=50)
        return self.symbols

    def get_current_prices(self, save=True):
        path = '/api/v4/spot/tickers'
        url = f'{self.url}{path}'
        self.sign({}, path)
        response = self.session.get(url)
        response.raise_for_status()
        data = response.json()
        for symbol in data:
            self.prices[self.standardize_symbol(symbol['currency_pair'])] = float(symbol['last'])
        if self.market:
            self.market.prices = json.dumps(self.prices)
            if save:
                self.market.save()
        return self.prices

    def get_klines(self, symbol:'MarketSymbol|str', interval:str, start:typing.Optional[datetime], end:typing.Optional[datetime]=None, limit=1000, retry=0):
        symbol_object = self.get_symbol_from_name(symbol) if isinstance(symbol, str) else symbol
        if not symbol_object:
            raise ValueError(f'Symbol not found: {symbol}')
        path = '/api/v4/spot/candlesticks'
        url = f'{self.url}{path}'
        payload = {
            'currency_pair': self.format_symbol(symbol_object.name),
            'symbol': self.format_symbol(symbol_object.name),
            'interval': self.format_interval(interval),
            'limit': limit
        }
        if start:
            payload['from'] = self.format_timestamp(start)
            payload.pop('limit', None)
        if end:
            payload['to'] = self.format_timestamp(end)
            payload.pop('limit', None)
        query = self.sign(payload, path)
        url = f'{url}?{query}'
        response = self.session.get(url)
        data = response.json()
        if isinstance(data, dict):
            logger.warning(f'Gate.io returned an error while fetching candles: {data}', extra={'market': self.name, 'type': 'MARKET'})
            return []
        return self.standardize_klines(data)

    def get_last_klines(self, symbol:str, interval:str, limit=100, retry=1, silent=True) -> list[list]:
        minutes = interval_to_minutes(interval)
        now = timezone.now() + timedelta(minutes=1)
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

    def init_websocket(self, symbol:str, interval:str, callback:typing.Callable, liveloop:'LiveLoop|None', retries:int=30):
        ws_uri = 'wss://api.gateio.ws/ws/v4/'
        try:
            ws = connect(ws_uri)
            ws.send(json.dumps({
                'time': self.format_timestamp(timezone.now()),
                'channel': 'spot.candlesticks',
                'event': 'subscribe',
                'payload': [self.format_interval(interval), self.format_symbol(symbol)]
            }))
            ack = json.loads(ws.recv())
            last_ping = timezone.now()
            while not self.stop_websocket_stream and not (liveloop and liveloop.should_stop()):
                try:
                    if (timezone.now() - last_ping) > timedelta(seconds=30):
                        ws.send(json.dumps({'time': self.format_timestamp(timezone.now()), 'channel': 'spot.ping'}))
                        last_ping = timezone.now()
                    data = json.loads(ws.recv(timeout=10))
                    if data.get('channel') == 'spot.pong':
                        continue
                except TimeoutError:
                    continue
                candle = self.format_ws_candle(data['result'])
                if candle['closed']:
                    candle['end'] = candle['start'] + timedelta(minutes=interval_to_minutes(interval))
                    callback(candle)
        except Exception as e:
            if retries < self.WS_MAX_RETRIES:
                time.sleep(1)
                retries += 1
                return self.init_websocket(symbol, interval, callback, liveloop, retries+1)
            msg = f'Failed to connect to websocket: {e}'
            logger.error(msg, extra={'market': self.name, 'type': 'MARKET'})
            raise MarketAPIError(msg) from e

    def get_match_engine_socket(self, symbol:str) -> ClientConnection:
        ws_uri = 'wss://api.gateio.ws/ws/v4/'
        ws = connect(ws_uri)
        ws.send(json.dumps({
            'time': self.format_timestamp(timezone.now()),
            'channel': 'spot.trades',
            'event': 'subscribe',
            'payload': [self.format_symbol(symbol)]
        }))
        ack = json.loads(ws.recv())
        return ws

    def init_match_engine(self, symbol:str, interval:str, callback:typing.Callable, liveloop:'LiveLoop|None', raw_callback:typing.Optional[typing.Callable]=None):
        ws = self.get_match_engine_socket(symbol)
        last_ping = timezone.now()
        engine = MatchEngine(interval, callback)
        retries = 30
        while not self.stop_websocket_stream and not (liveloop and liveloop.should_stop()):
            if last_ping - timezone.now() > timedelta(seconds=30):
                ws.send(json.dumps({'time': self.format_timestamp(timezone.now()), 'channel': 'spot.ping'}))
                last_ping = timezone.now()
            try:
                data = json.loads(ws.recv(timeout=10))
                if data.get('channel') == 'spot.pong':
                    continue
            except TimeoutError:
                continue
            except (ConnectionClosed, ConnectionClosedOK):
                ws = self.get_match_engine_socket(symbol)
                continue
            except:
                if retries > self.WS_MAX_RETRIES:
                    logger.error('Failed to connect to websocket', extra={'market': self.name, 'type': 'MARKET'})
                    raise MarketAPIError('Failed to connect to websocket')
                time.sleep(1)
                ws = self.get_match_engine_socket(symbol)
                retries += 1
                continue
            if raw_callback:
                raw_callback(data)
            trade = self.format_match(data['result'])
            engine.on_match(trade)

    def place_market_order(self, symbol:'MarketSymbol|str', side:typing.Literal['buy', 'sell'], funds:typing.Optional[str]=None, quantity:typing.Optional[str]=None, validate=True):
        symbol_object = self.get_symbol_from_name(symbol) if isinstance(symbol, str) else symbol
        if not symbol_object:
            raise ValueError(f'Symbol not found: {symbol}')
        path = '/api/v4/spot/orders'
        url = f'{self.url}{path}'
        payload = {
            'currency_pair': self.format_symbol(symbol_object.name),
            'side': side,
            'type': 'market',
            'account': 'spot',
            'time_in_force': 'ioc'
        }
        if funds:
            payload['amount'] = funds
        if quantity:
            payload['amount'] = quantity
        self.sign(payload, path=path, method='POST')
        response = self.session.post(url, data=json.dumps(payload))
        data = response.json()
        if not data.get('id'):
            msg = data.get('message').lower()
            if 'not enough' in msg:
                raise InsufficientBalance(f'Insufficient funds to place order on {self.name}: {data.get("retMsg")}')
            if 'too many decimals' in msg:
                raise RejectedOrder(f'Order was rejected by the exchange {self.name}: {data.get("retMsg")}')
            raise OrderPlacementError(data.get('retMsg'))
        order = self.prep_order(data)
        if side == 'buy' and not order.funds and funds:
            order.funds = float(funds)
        return order

    def get_order(self, symbol:'MarketSymbol|str|None', order:'Order|str|int', retries=0) -> 'Order':
        if not isinstance(order, str) and not isinstance(order, int):
            order_id = order.oid
        else:
            order_id = order
        path = f'/api/v4/spot/orders/{order_id}'
        url = f'{self.url}{path}'
        self.sign({}, path)
        response = self.session.get(url)
        response.raise_for_status()
        data = response.json()
        if not data.get('id'):
            if retries < 3:
                time.sleep(0.5)
                return self.get_order(symbol, order, retries+1)
            raise OrderPostProcessingError(f'Error fetching order: {data}')
        order = self.prep_order(data)
        return order

    def get_full_orderbook(self, symbol:'MarketSymbol|str', limit=5000) -> dict:
        symbol_object = self.get_symbol_from_name(symbol) if isinstance(symbol, str) else symbol
        if not symbol_object:
            raise ValueError(f'Symbol not found: {symbol}')
        path = f'/api/v4/spot/order_book'
        url = f'{self.url}{path}'
        payload = {
            'currency_pair': self.format_symbol(symbol_object.name),
            'interval': 0,
            'limit': limit
        }
        query = self.sign(payload, path)
        url = f'{url}?{query}'
        response = self.session.get(url)
        data = response.json()
        try:
            pre_ob = { 'asks': data['asks'], 'bids': data['bids'] }
            orderbook = self.format_orderbook_snapshot(pre_ob)
        except Exception as e:
            raise MarketAPIError(f'Failed to process orderbook: {traceback.format_exc()}')
        return orderbook

    def format_orderbook_snapshot(self, orderbook:dict) -> dict:
        return {
            'bids': [{ 'price': Decimal(price), 'size': Decimal(size), 'count': 1 } for price, size in orderbook['bids']],
            'asks': [{ 'price': Decimal(price), 'size': Decimal(size), 'count': 1 } for price, size in orderbook['asks']],
        }

    def format_orderbook_update(self, orderbook:dict) -> dict:
        return {
            'bids': [{ 'price': Decimal(price), 'size': Decimal(size), 'count': 1 } for price, size in orderbook['bids']],
            'asks': [{ 'price': Decimal(price), 'size': Decimal(size), 'count': 1 } for price, size in orderbook['asks']],
        }

    def init_orderbook_websocket(self, symbol:'MarketSymbol|str', callback:typing.Callable, liveloop:'LiveLoop|None'=None, retries:int=30):
        if isinstance(symbol, str):
            symbol_obj = self.get_symbol_from_name(symbol)
        else:
            symbol_obj = symbol
        if not symbol_obj:
            raise ValueError(f'Symbol not found: {symbol}')
        ws_uri = 'wss://api.gateio.ws/ws/v4/'
        try:
            ws = connect(ws_uri)
            ws.send(json.dumps({
                'time': self.format_timestamp(timezone.now()),
                'channel': 'spot.order_book_update',
                'event': 'subscribe',
                'payload': [self.format_symbol(symbol_obj.name), '100ms']
            }))
            ack = json.loads(ws.recv())
            while not self.stop_websocket_stream and not (liveloop and liveloop.should_stop()):
                try:
                    data = json.loads(ws.recv(timeout=1))
                except TimeoutError:
                    continue
                if not data.get('result'):
                    logger.warning(f'Received a message in an unrecognized format from {self.name} websocket: {data}', extra={'market': self, 'type': 'MARKET'})
                    continue
                pre_ob = { 'asks': data['result']['a'], 'bids': data['result']['b']}
                orderbook = self.format_orderbook_update(pre_ob)
                callback(orderbook)
        except Exception as e:
            if retries < self.WS_MAX_RETRIES:
                time.sleep(1)
                retries += 1
                return self.init_orderbook_websocket(symbol, callback, liveloop, retries+1)
            msg = f'Failed to connect to websocket: {e}'
            logger.error(msg, extra={'market': self.name, 'type': 'MARKET'})
            raise MarketAPIError(f'Failed to connect to websocket: {traceback.format_exc()}')

    def get_equity(self, save=True):
        prices = self.get_current_prices(save=False)
        if not prices:
            prices = json.loads(self.market.prices or '{}')
        equity = self.capital + sum([ self.assets.get(asset, 0) * prices.get(asset+'-USDT', 0) for asset in self.assets ])
        if self.account and self.account.equity != equity:
            self.account.equity = equity
            if save:
                self.account.save()
        return equity

    def prep_order(self, order:dict) -> 'Order':
        from quantapi.models import Order
        try:
            return Order(
                oid=order['id'],
                status=order['finish_as'].upper(),
                order_type=order['type'].upper(),
                deal_size=float(order['filled_amount']),
                deal_funds=float(order['filled_total']),
                price=float(order['fill_price']),
                side=order['side'].upper(),
                market_timestamp=self.standardize_timestamp(order['create_time']),
                symbol=self.get_symbol_from_name(self.standardize_symbol(order['currency_pair'])),
                account=self.account,
                details=json.dumps(order, indent=2)
            )
        except KeyError as e:
            key = str(e).replace('\'', '')
            raise MarketAPIUnrecognizedResponse(key, order)

    def prep_symbol(self, symbol:dict) -> 'MarketSymbol':
        from quantapi.models import MarketSymbol
        symbol_object = MarketSymbol(
            market=self.market,
            name=self.standardize_symbol(symbol['id']),
            base=symbol['base'],
            quote=symbol['quote'],
            base_precision=float(symbol.get('amoun_precision', 0)),
            quote_precision=float(symbol.get('precision', 0)),
            spot_trading_enabled=symbol['trade_status'] == 'tradable',
            details=json.dumps(symbol, indent=2)
        )
        return symbol_object

    def format_symbol(self, name:str) -> str:
        return name.upper().replace('-', '_')

    def standardize_symbol(self, symbol:str) -> str:
        return symbol.upper().replace('_', '-')

    def format_timestamp(self, ts:datetime) -> int:
        return int(ts.timestamp())

    def standardize_timestamp(self, ts:str) -> datetime:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)

    def format_interval(self, interval:str) -> str:
        return {
            '1 min': '1m',
            '5 min': '5m',
            '15 min': '15m',
            '30 min': '30m',
            '1 hour': '1h',
            '4 hour': '4h',
            '1 day': '1d',
            '1 week': '7d',
            '1 month': '30d',
        }[interval]

    def standardize_klines(self, data:list) -> list[list]:
        # tv is volume in quote currency
        return [[
            self.standardize_timestamp(str(ts)),
            float(o),
            float(h),
            float(l),
            float(c),
            float(v)
        ] for ts, tv, c, h, l, o, v, t in data if t == 'true']

    def get_symbol_from_name(self, name:str) -> 'MarketSymbol|None':
        return self.symbols.get(name)

    def format_ws_candle(self, data:dict):
        return {
            'time': self.standardize_timestamp(data['t']),
            'start': self.standardize_timestamp(data['t']),
            'open': float(data['o']),
            'high': float(data['h']),
            'low': float(data['l']),
            'close': float(data['c']),
            'volume': float(data['a']),
            'closed': data['w'],
        }

    def format_match(self, data:dict):
        return {
            'time': self.standardize_timestamp(data['create_time']),
            'price': float(data['price']),
            'size': float(data['amount']),
            'maker': True if data['side'] == 'buy' else False,
        }

    def has_symbol(self, symbol: str) -> bool:
        symbol = self.standardize_symbol(symbol)
        return symbol in self.symbols or symbol.split('-')[0] in self.symbols
