from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import hmac
import json
from threading import Event
import time
import traceback
import pytz
import requests
from logger import logger
from markets.errors import InsufficientBalance, KlineFetchFailed, MarketAPIError, MarketAPIUnavailable, OrderPlacementError, OrderPostProcessingError, RejectedOrder, SymbolNotInMarket
from markets.interface import IMarket
from logger import logger
import base64

from django.utils import timezone
import typing
from websockets.sync.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK
from match import MatchEngine
from models import interval_to_minutes
if typing.TYPE_CHECKING:
    from quantapi.models import MarketAccount, MarketSymbol, Market


class OKXMarket(IMarket):
    name = 'OKX'

    def __init__(self, config: dict, account: 'MarketAccount|None', market: 'Market|None'=None):
        self.url = 'https://www.okx.com'
        self.api_key = config.get('API_KEY', '')
        self.api_secret = config.get('API_SECRET', '')
        self.api_passphrase = config.get('API_PASSPHRASE', '')
        self.recv_window = 60000
        self.session = requests.Session()
        self.session.headers.update({
            'OK-ACCESS-KEY': self.api_key,
            'OK-ACCESS-PASSPHRASE': self.api_passphrase,
            'Content-Type': 'application/json'
        })
        self.private = bool(self.api_key and self.api_secret and self.api_passphrase)

        self.account = account
        self.market = account.market if account else market  # type: ignore
        self.spot_trading_enabled = True
        self.capital = 0
        self.symbols = {}
        self.assets = {}
        self.prices = {}
        self.authenticated = True
        self.stop_websocket_stream = False
        self.orderbook_seq = 0

        try:
            if self.private:
                self.get_account()
            self.get_symbols()
        except requests.ConnectionError as exc:
            raise MarketAPIUnavailable(f'Could not connect to {self.name} API') from exc

    def sign(self, payload:dict, path:str, method:str='GET') -> str:
        if not payload:
            payload = {}
        payload_str = json.dumps(payload) if payload else ''
        now = self.format_timestamp(timezone.now())
        query = f'{now}{method}{path}{payload_str}'
        hash = hmac.new(bytes(self.api_secret, "utf-8"), query.encode("utf-8"), hashlib.sha256)
        signature = base64.b64encode(hash.digest()).decode()
        self.session.headers['OK-ACCESS-TIMESTAMP'] = now
        self.session.headers['OK-ACCESS-SIGN'] = signature
        return query

    def get_account(self, save=True):
        path = '/api/v5/account/balance'
        url = self.url + path
        self.sign({}, path)
        response = self.session.get(url)
        if not response.ok:
            raise MarketAPIError(f'Failed to fetch account data from {self.name}: {response.text}')
        data = response.json()['data'][0]['details']
        for asset in data:
            self.assets[asset['ccy']] = float(asset['availBal'])
        self.capital = self.assets.get('USDT', 0)
        if self.account:
            self.account.capital = self.capital
            self.account.assets = json.dumps(self.assets)
            if save:
                self.account.save()
        return data

    def get_futures_symbols(self):
        path = '/api/v5/public/instruments?instType=SWAP'
        url = f'{self.url}{path}'
        self.sign({}, path)
        response = self.session.get(url)
        response.raise_for_status()
        data = response.json()
        data = data['data']

        self.futures_symbols = { self.standardize_symbol(symbol['instFamily']) + '.F': self.prep_futures_symbol(symbol) for symbol in data if symbol['settleCcy'] == 'USDT' }
        if self.market:
            from quantapi.models import MarketSymbol
            x = MarketSymbol.objects.bulk_create(self.futures_symbols.values(), update_conflicts=True, update_fields=[
                'spot_trading_enabled', 
                'margin_trading_enabled', 
                'details',
                'base_precision',
                'quote_precision',
            ], unique_fields=['name', 'market', 'contract_type'])
        return self.futures_symbols

    def get_symbols(self):
        path = '/api/v5/public/instruments?instType=SPOT'
        url = f'{self.url}{path}'
        self.sign({}, path)
        response = self.session.get(url)
        response.raise_for_status()
        data = response.json()
        data = data['data']
        self.symbols = { self.standardize_symbol(symbol['instId']): self.prep_symbol(symbol) for symbol in data if symbol['quoteCcy'] == 'USDT' }
        if self.market:
            from quantapi.models import MarketSymbol
            MarketSymbol.objects.bulk_create(self.symbols.values(), update_conflicts=True, update_fields=[
                'spot_trading_enabled', 
                'margin_trading_enabled', 
                'details',
                'base_precision',
                'quote_precision',
            ], unique_fields=['name', 'market', 'contract_type'], batch_size=50)
        self.futures_symbols = self.get_futures_symbols()
        return self.symbols, self.futures_symbols

    def get_current_prices(self, save=True):
        path = '/api/v5/market/tickers?instType=SPOT'
        url = f'{self.url}{path}'
        self.sign({}, path)
        response = self.session.get(url)
        response.raise_for_status()
        data = response.json()
        data = data['data']
        for symbol in data:
            if not symbol['instId'].endswith('USDT'):
                continue
            self.prices[self.standardize_symbol(symbol['instId'])] = float(symbol['last'])
        if self.market:
            self.market.prices = json.dumps(self.prices)
            self.market.prices_updated = datetime.now(tz=pytz.UTC)
            if save:
                self.market.save()
        return self.prices

    def get_klines(self, symbol:'MarketSymbol|str', interval:str, start:datetime, end:typing.Optional[datetime]=None, limit=1000, retry=0):
        symbol_object = self.get_symbol_from_name(symbol) if isinstance(symbol, str) else symbol
        contract_type = symbol_object.contract_type if symbol_object else None
        if not symbol_object:
            raise ValueError(f'Symbol not found: {symbol}')
        now = timezone.now()
        start = start.astimezone(pytz.UTC)
        end = end.astimezone(pytz.UTC) if end else now
        freq_m = interval_to_minutes(interval)
        candle_c = (now - start) / timedelta(minutes=freq_m)
        if candle_c > 1440:
            logger.warning('BYBIT only offers the latest 1440 candles for a given interval. Modifying start time to fetch the latest 1440 candles.', extra={'market': self.name, 'type': 'MARKET'})
            start = now - timedelta(minutes=freq_m*1440)
        query = {
            'bar': self.format_interval(interval),
            'before': int(start.timestamp() * 1000),
            'instId': self.format_symbol(symbol_object.name) + ('-SWAP' if contract_type == 'FUTURES' else ''),
            'limit': limit,
        }
        if end:
            query['after'] = int(end.timestamp() * 1000)
        path = f'/api/v5/market/candles?{"&".join([f"{k}={v}" for k, v in query.items()])}'
        url = f'{self.url}{path}'
        self.sign({}, path)
        response = self.session.get(url)
        data = response.json()
        data = data['data']
        return self.standardize_klines(data)

    def get_last_klines(self, symbol:'MarketSymbol|str', interval:str, limit=100, retry=1, silent=True) -> list[list]:
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

    def init_websocket(self, symbol:str, interval:str, callback:typing.Callable, liveloop, retries:int=30):
        ws_uri = 'wss://ws.okx.com:8443/ws/v5/business'
        try:
            ws = connect(ws_uri)
            ws.send(json.dumps({
                'op': 'subscribe',
                'args': [{
                    'channel': f'candle{self.format_interval(interval)}',
                    'instId': self.format_symbol(symbol),
                }]
            }))
            ack = json.loads(ws.recv())
            if ack.get('op') == 'error':
                raise MarketAPIError(f'Failed to subscribe to websocket: {ack}')
            while not self.stop_websocket_stream and not (liveloop and liveloop.should_stop()):
                try:
                    data = json.loads(ws.recv(timeout=10))
                except TimeoutError:
                    continue
                if not data.get('data'):
                    logger.warning(f'Received a message in an unrecognized format from {self.name} websocket: {data}', extra={'market': self, 'type': 'MARKET'})
                    continue
                candle = self.format_ws_candle(data['data'][0])
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
            raise MarketAPIError(f'Failed to connect to websocket: {traceback.format_exc()}')

    def get_match_engine_socket(self, symbol:'MarketSymbol|str') -> ClientConnection:
        if isinstance(symbol, str):
            symbol_object = self.get_symbol_from_name(symbol)
            if not symbol_object:
                raise SymbolNotInMarket(f'{symbol} not found in {self.name}')
        else:
            symbol_object = symbol

        ws_uri = 'wss://ws.okx.com:8443/ws/v5/business'
        while True:
            try:
                ws = connect(ws_uri)
                ws.send(json.dumps({
                    'op': 'subscribe',
                    'args': [{
                        'channel': 'trades-all',
                        'instId': self._format_instId(symbol_object),
                    }]
                }))
            except TimeoutError:
                time.sleep(5)
                continue
            ack = json.loads(ws.recv())
            if ack.get('event') == 'error':
                raise MarketAPIError(f'Failed to subscribe to websocket: {ack}')
            return ws

    def init_match_engine(self, symbol:'MarketSymbol', interval:str, callback:typing.Callable, stop_event: Event, raw_callback:'typing.Optional[typing.Callable]'=None, ticker_callback:'typing.Optional[typing.Callable]'=None):
        ws = self.get_match_engine_socket(symbol)
        engine = MatchEngine(symbol, interval, callback, ticker_callback)
        retries = 30
        while not stop_event.is_set():
            try:
                data = json.loads(ws.recv(timeout=10))
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
            if not data.get('data'):
                logger.warning(f'Received a message in an unrecognized format from {self.name} websocket: {data}', extra={'market': self, 'type': 'MARKET'})
                continue
            if raw_callback:
                raw_callback(data)
            trade = self.format_match(data['data'][0])
            engine.on_match(trade)

    def place_market_order(self, symbol:'MarketSymbol|str', side:typing.Literal['buy', 'sell'], funds:typing.Optional[str]=None, quantity:typing.Optional[str]=None, validate=True):
        symbol_object = self.get_symbol_from_name(symbol) if isinstance(symbol, str) else symbol
        if not symbol_object:
            raise ValueError(f'Symbol not found: {symbol}')
        path = '/api/v5/trade/order'
        url = f'{self.url}{path}'
        payload = {
            'instId': self.format_symbol(symbol_object.name),
            'tdMode': 'cash',
            'side': side,
            'ordType': 'market',
        }
        if funds:
            payload['sz'] = funds
        if quantity:
            payload['sz'] = quantity
        self.sign(payload, path, method='POST')
        response = self.session.post(url, data=json.dumps(payload).rstrip('"').lstrip('"'))
        data = response.json()
        if not data.get('data'):
            raise OrderPlacementError(f'Unrecognized payload returned while placing order on {self.name}: {data}')
        data = data['data'][0]
        msg = data.get('sMsg', '').lower()
        if 'insufficient' in msg:
            raise InsufficientBalance(f'Insufficient funds to place order on {self.name}: {msg}')
        elif 'too many decimals' in msg or 'exceeded' in msg:
            raise RejectedOrder(f'Order was rejected by the exchange {self.name}: {msg}')
        elif msg != 'order placed':
            raise OrderPlacementError(data.get('retMsg'))

        return self.get_order(symbol_object, data['ordId'])

    def get_order(self, symbol:'MarketSymbol|str', order, retries=0):
        from quantapi.models import MarketSymbol
        if not isinstance(order, str) and not isinstance(order, int):
            order_id = order.oid
        else:
            order_id = order
        if isinstance(symbol, MarketSymbol):
            symbol_name = symbol.name
        else:
            symbol_name = symbol
        path = f'/api/v5/trade/order?ordId={order_id}&instId={self.format_symbol(symbol_name)}'
        url = f'{self.url}{path}'
        self.sign({}, path)
        response = self.session.get(url)
        data = response.json()
        try:
            order_payload = data['data'][0]
        except IndexError:
            if retries > 3:
                raise ValueError('Order not found:' + str(order))
            time.sleep(0.5)
            return self.get_order(symbol, order, retries+1)
        try:
            order = self.prep_order(order_payload)
        except Exception as e:
            raise OrderPostProcessingError(f'Failed to process order: {e}')
        return order

    def get_full_orderbook(self, symbol:'MarketSymbol|str', limit=5000) -> dict:
        symbol_object = self.get_symbol_from_name(symbol) if isinstance(symbol, str) else symbol
        if not symbol_object:
            raise ValueError(f'Symbol not found: {symbol}')
        if symbol_object.contract_type == symbol_object.ContractType.FUTURES:
            path = f'/api/v5/market/books-full?instId={self.format_symbol(symbol_object.name)}-SWAP&sz={limit}'
        elif symbol_object.contract_type == symbol_object.ContractType.SPOT:
            path = f'/api/v5/market/books-full?instId={self.format_symbol(symbol_object.name)}&sz={limit}'
        else:
            raise ValueError(f'Unknown contract type for symbol {symbol_object.name}')
        url = f'{self.url}{path}'
        self.sign({}, path)
        response = self.session.get(url)
        data = response.json()
        try:
            orderbook = self.format_orderbook_snapshot(data['data'][0])
        except Exception as e:
            raise MarketAPIError(f'Failed to process orderbook: {e} {data}')
        return orderbook

    def format_orderbook_snapshot(self, orderbook:dict) -> dict:
        return {
            'bids': [{ 'price': Decimal(price), 'size': Decimal(size), 'count': int(count) } for price, size, count in orderbook['bids']],
            'asks': [{ 'price': Decimal(price), 'size': Decimal(size), 'count': int(count) } for price, size, count in orderbook['asks']],
        }

    def format_orderbook_update(self, orderbook:dict) -> dict:
        if orderbook['seqId'] <= self.orderbook_seq:
            return { 'bids': [], 'asks': [] }
        return {
            'bids': [{ 'price': Decimal(price), 'size': Decimal(size), 'count': int(count) } for price, size, _, count in orderbook['bids']],
            'asks': [{ 'price': Decimal(price), 'size': Decimal(size), 'count': int(count) } for price, size, _, count in orderbook['asks']],
        }

    def _format_instId(self, symbol:'MarketSymbol') -> str:
        mapping = {
            'SPOT': '',
            'FUTURES': '-SWAP',
        }
        return self.format_symbol(symbol.name) + mapping[symbol.contract_type]

    def init_orderbook_websocket(self, symbol:'MarketSymbol|str', callback:typing.Callable, liveloop=None, retries:int=30):
        if isinstance(symbol, str):
            symbol_obj = self.get_symbol_from_name(symbol)
        else:
            symbol_obj = symbol
        if not symbol_obj:
            raise ValueError(f'Symbol not found: {symbol}')
        ws_uri = 'wss://ws.okx.com:8443/ws/v5/public'
        try:
            ws = connect(ws_uri)
            ws.send(json.dumps({
                'op': 'subscribe',
                'args': [{
                    'channel': 'books',
                    'instId': self._format_instId(symbol_obj),
                }]
            }))
            ack = json.loads(ws.recv())
            if ack.get('op') == 'error':
                ws.close()
                raise MarketAPIError(f'Failed to subscribe to websocket: {ack}')
            while not self.stop_websocket_stream and not (liveloop and liveloop.should_stop()):
                try:
                    data = json.loads(ws.recv(timeout=1))
                except TimeoutError:
                    continue
                if not data.get('data'):
                    logger.warning(f'Received a message in an unrecognized format from {self.name} websocket: {data}', extra={'market': self, 'type': 'MARKET'})
                    continue
                orderbook = self.format_orderbook_update(data['data'][0])
                self.orderbook_seq = data['data'][0]['seqId']
                callback(orderbook)
        except Exception as e:
            if retries < self.WS_MAX_RETRIES:
                time.sleep(1)
                retries += 1
                return self.init_orderbook_websocket(symbol, callback, liveloop, retries+1)
            msg = f'Failed to connect to websocket: {e}'
            logger.error(msg, extra={'market': self.name, 'type': 'MARKET'})
            ws.close()
            raise MarketAPIError(f'Failed to connect to websocket: {traceback.format_exc()}')
        ws.close()

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

    def prep_order(self, order:dict):
        raise NotImplementedError
        from quantapi.models import Order
        return Order(
            oid=order['ordId'],
            status=order['state'].upper(),
            order_type=order['ordType'].upper(),
            deal_size=float(order['fillSz']),
            deal_funds=float(order['sz']) if order['side'] == 'buy' else None,
            price=float(order['fillPx']),
            side=order['side'].upper(),
            market_timestamp=self.standardize_timestamp(order['fillTime']),
            symbol=self.get_symbol_from_name(self.standardize_symbol(order['instId'])),
            details=json.dumps(order, indent=2),
            account=self.account
        )

    def prep_symbol(self, symbol:dict) -> 'MarketSymbol':
        from quantapi.models import MarketSymbol
        symbol_object = MarketSymbol(
            market=self.market,
            name=self.standardize_symbol(symbol['instId']),
            base=symbol['baseCcy'],
            quote=symbol['quoteCcy'],
            base_precision=float(symbol.get('tickSz', 0)),
            quote_precision=float(symbol.get('lotSz', 0)),
            spot_trading_enabled=symbol['state'] == 'live',
            details=json.dumps(symbol, indent=2),
            contract_type=MarketSymbol.ContractType.SPOT
        )
        return symbol_object

    def prep_futures_symbol(self, symbol:dict) -> 'MarketSymbol':
        from quantapi.models import MarketSymbol
        symbol_object = MarketSymbol(
            market=self.market,
            name=self.standardize_symbol(symbol['instFamily']),
            base=symbol['ctValCcy'],
            quote=symbol['settleCcy'],
            base_precision=float(symbol.get('tickSz', 0)),
            quote_precision=float(symbol.get('lotSz', 0)),
            spot_trading_enabled=symbol['state'] == 'live',
            details=json.dumps(symbol, indent=2),
            contract_type=MarketSymbol.ContractType.FUTURES
        )
        return symbol_object

    def format_symbol(self, name:str) -> str:
        return name.upper()

    def standardize_symbol(self, symbol:str) -> str:
        return symbol.upper().replace('-', '').replace('USDT', '-USDT')

    def format_timestamp(self, ts:datetime) -> str:
        # e.g : 2020-12-08T09:08:57.715Z
        return ts.isoformat('T', timespec='milliseconds').replace('+00:00', 'Z')

    def standardize_timestamp(self, ts:str) -> datetime:
        return datetime.fromtimestamp(int(ts) // 1000, tz=pytz.UTC)

    def format_interval(self, interval:str) -> str:
        return {
            '1 min': '1m',
            '5 min': '5m',
            '15 min': '15m',
            '30 min': '30m',
            '1 hour': '1H',
            '4 hour': '4H',
            '12 hour': '12H',
            '1 day': '1D',
            '1 week': '1W',
            '1 month': '1M',
        }[interval]

    def standardize_klines(self, data:list) -> list[list]:
        return [[
            self.standardize_timestamp(str(ts)),
            float(o),
            float(h),
            float(l),
            float(c),
            float(v)
        ] for ts, o, h, l, c, v, t, x, y in data]

    def get_symbol_from_name(self, name:str) -> 'MarketSymbol|None':
        return self.symbols.get(name)

    def format_ws_candle(self, data:list):
        candle = {
            'time': self.standardize_timestamp(data[0]),
            'start': self.standardize_timestamp(data[0]),
            'open': float(data[1]),
            'high': float(data[2]),
            'low': float(data[3]),
            'close': float(data[4]),
            'volume': float(data[5]),
            'closed': bool(int(data[8])),
        }
        return candle

    def format_match(self, data:dict) -> dict:
        return {
            'time': self.standardize_timestamp(data['ts']),
            'price': float(data['px']),
            'size': float(data['sz']),
            'maker': True if data['side'] == 'buy' else False,
        }

    def has_symbol(self, symbol: str) -> bool:
        symbol = self.standardize_symbol(symbol)
        return symbol in self.symbols or symbol.split('-')[0] in self.symbols
