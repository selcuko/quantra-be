from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import hmac
import json
import time
import requests
from logger import logger
from markets.errors import InsufficientBalance, KlineFetchFailed, MarketAPIError, MarketAPIUnavailable, OrderPlacementError, OrderPostProcessingError, RejectedOrder
from markets.interface import IMarket
from logger import logger
from django.utils import timezone
import typing
from websockets.sync.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK
from match import MatchEngine
from models import interval_to_minutes
if typing.TYPE_CHECKING:
    from quantapi.models import MarketSymbol, Order, MarketAccount
    from liveloop import LiveLoop
    from loopgroup import LoopGroup


class BybitMarket(IMarket):
    name = 'Bybit'

    def __init__(self, config: dict, account: 'MarketAccount'):
        self.url = 'https://api.bybit.com'
        self.api_key = config['API_KEY']
        self.api_secret = config['API_SECRET']
        self.recv_window = 60000
        self.session = requests.Session()
        self.session.headers.update({
            'X-BAPI-API-KEY': config['API_KEY'],
            'X-BAPI-SIGN-TYPE': '2',
            'X-BAPI-RECV-WINDOW': str(self.recv_window),
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

        try:
            self.get_account()
            self.get_symbols()
        except requests.ConnectionError as exc:
            raise MarketAPIUnavailable(f'Could not connect to {self.name} API') from exc
        self.orderbook_seq = 0

    def sign(self, payload:dict, method:str='GET') -> str:
        if not payload:
            payload = {}
        now = self.format_timestamp(timezone.now())
        if method == 'GET':
            query = '&'.join([f'{k}={v}' for k, v in payload.items()])
            query_str = str(now) + self.api_key + str(self.recv_window) + query
        else:
            query = json.dumps(payload)
            query_str = str(now) + self.api_key + str(self.recv_window) + query
        hash = hmac.new(bytes(self.api_secret, "utf-8"), query_str.encode("utf-8"), hashlib.sha256)
        signature = hash.hexdigest()
        self.session.headers['X-BAPI-TIMESTAMP'] = self.format_timestamp(timezone.now())
        self.session.headers['X-BAPI-SIGN'] = signature
        return query

    def get_account(self, save=True):
        url = f'{self.url}/v5/asset/transfer/query-account-coins-balance'
        payload = {
            'accountType': 'UNIFIED'
        }
        query = self.sign(payload)
        uri = f'{url}?{query}'
        response = self.session.get(uri)
        response.raise_for_status()
        data = response.json()
        if data.get('retMsg') not in ['OK', 'success']:
            raise ValueError(data)
        data = data['result']['balance']
        for symbol in data:
            self.assets[symbol['coin']] = float(symbol['walletBalance'])
        self.capital = self.assets.get('USDT', 0)
        if self.account:
            self.account.capital = self.capital
            self.account.assets = json.dumps(self.assets)
            if save:
                self.account.save()

    def get_symbols(self) -> dict[str, 'MarketSymbol']:
        url = f'{self.url}/v5/market/instruments-info'
        payload = {
            'category': 'spot'
        }
        query = self.sign(payload)
        uri = f'{url}?{query}'
        response = self.session.get(uri)
        response.raise_for_status()
        data = response.json()
        if data.get('retMsg') not in ['OK', 'success']:
            raise ValueError(data)
        data = data['result']['list']
        self.symbols = { self.standardize_symbol(symbol['symbol']): self.prep_symbol(symbol) for symbol in data if symbol['symbol'].endswith('USDT') }
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

    def get_current_prices(self, save=True) -> dict:
        url = f'{self.url}/v5/market/tickers'
        payload = {
            'category': 'spot'
        }
        query = self.sign(payload)
        uri = f'{url}?{query}'
        response = self.session.get(uri)
        response.raise_for_status()
        data = response.json()
        if data.get('retMsg') not in ['OK', 'success']:
            raise ValueError(data)
        data = data['result']['list']
        for symbol in data:
            self.prices[self.standardize_symbol(symbol['symbol'])] = float(symbol['lastPrice'])
        if self.market:
            self.market.prices = json.dumps(self.prices)
            if save:
                self.market.save()
        return self.prices

    def get_klines(self, symbol:'MarketSymbol|str', interval:str, start:datetime, end:typing.Optional[datetime]=None, limit:int=1000, retry:int=0) -> list[list]:
        symbol_object = self.get_symbol_from_name(symbol) if isinstance(symbol, str) else symbol
        if not symbol_object:
            raise ValueError(f'Symbol not found: {symbol}')
        url = f'{self.url}/v5/market/kline'
        payload = {
            'category': 'spot',
            'symbol': self.format_symbol(symbol_object.name),
            'interval': self.format_interval(interval),
            'start': self.format_timestamp(start),
            'limit': limit
        }
        if end:
            payload['end'] = self.format_timestamp(end)
        query = self.sign(payload)
        uri = f'{url}?{query}'
        response = self.session.get(uri)
        response.raise_for_status()
        data = response.json()
        if data.get('retMsg') not in ['OK', 'success']:
            raise ValueError(data)
        data = data['result']['list']
        return self.standardize_klines(data)

    def get_last_klines(self, symbol:'MarketSymbol | str', interval:str, limit:int=100, retry:int=1, silent=True) -> list[list]:
        minutes = interval_to_minutes(interval)
        now = timezone.now().replace(second=0, microsecond=0) + timedelta(minutes=1)
        start = now - timedelta(minutes=minutes*limit+1)
        klines = self.get_klines(
            symbol=symbol,
            interval=interval,
            start=start,
            end=now,
            limit=limit,
        )
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

    def init_websocket(self, symbol:str, interval:str, callback:typing.Callable, liveloop:'LiveLoop|LoopGroup|None', retries:int=1):
        ws_uri = 'wss://stream.bybit.com/v5/public/spot'
        try:
            ws = connect(ws_uri)
            ws.send(json.dumps({
                'op': 'subscribe',
                'args': [f'kline.{self.format_interval(interval)}.{self.format_symbol(symbol)}']
            }))
            ack = json.loads(ws.recv())
            last_ping = timezone.now()
            while not self.stop_websocket_stream and not (liveloop and liveloop.should_stop()):
                try:
                    if (timezone.now() - last_ping) > timedelta(seconds=30):
                        ws.send(json.dumps({'op': 'ping'}))
                        last_ping = timezone.now()
                    data = json.loads(ws.recv(timeout=10))
                    if data.get('op') == 'pong':
                        continue
                except TimeoutError:
                    continue
                candle = self.format_ws_candle(data['data'][0])
                if candle['closed']:
                    callback(candle)
        except Exception as e:
            if retries < self.WS_MAX_RETRIES:
                time.sleep(1)
                retries += 1
                return self.init_websocket(symbol, interval, callback, liveloop, retries+1)
            msg = f'Failed to connect to websocket: {e}'
            logger.error(msg, extra={'market': self.name, 'type': 'MARKET'})
            raise MarketAPIError(msg) from e
        ws.close()

    def get_match_engine_socket(self, symbol:str) -> ClientConnection:
        ws_uri = 'wss://stream.bybit.com/v5/public/spot'
        base = self.format_symbol(symbol.split('-')[0])
        ws = connect(ws_uri)
        ws.send(json.dumps({
            'op': 'subscribe',
            'args': [f'publicTrade.{self.format_symbol(symbol)}']
        }))
        ack = json.loads(ws.recv())
        if not ack.get('success'):
            raise MarketAPIError(f'Failed to subscribe to websocket: {ack}')
        return ws

    def init_match_engine(self, symbol:str, interval:str, callback:typing.Callable, liveloop:'LiveLoop|LoopGroup|None'):
        ws = self.get_match_engine_socket(symbol)
        last_ping = timezone.now()
        engine = MatchEngine(interval, callback)
        retries = 30
        while not self.stop_websocket_stream and not (liveloop and liveloop.should_stop()):
            if last_ping - timezone.now() > timedelta(seconds=30):
                ws.send(json.dumps({'op': 'ping'}))
                last_ping = timezone.now()
            try:
                data = json.loads(ws.recv(timeout=10))
                if data.get('op') == 'pong':
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
            trade = self.format_match(data['data'][0])
            engine.on_match(trade)
        ws.close()

    def place_market_order(self, symbol:'MarketSymbol|str', side:typing.Literal['buy', 'sell'], funds:typing.Optional[str]=None, quantity:typing.Optional[str]=None, validate=True) -> 'Order':
        symbol_object = self.get_symbol_from_name(symbol) if isinstance(symbol, str) else symbol
        if not symbol_object:
            raise ValueError(f'Symbol not found: {symbol}')
        url = f'{self.url}/v5/order/create'
        payload = {
            'category': 'spot',
            'symbol': self.format_symbol(symbol_object.name),
            'side': side.title(),
            'orderType': 'Market',
        }
        if funds:
            payload['qty'] = funds
        if quantity:
            payload['qty'] = quantity
        self.sign(payload, method='POST')
        response = self.session.post(url, data=json.dumps(payload).rstrip('"').lstrip('"'))
        response.raise_for_status()
        data = response.json()
        if data.get('retMsg') not in ['OK', 'success']:
            if 'insufficient' in data.get('retMsg').lower():
                raise InsufficientBalance(f'Insufficient funds to place order on {self.name}: {data.get("retMsg")}')
            if 'too many decimals' in data.get('retMsg').lower() or 'exceeded' in data.get('retMsg').lower():
                raise RejectedOrder(f'Order was rejected by the exchange {self.name}: {data.get("retMsg")}')
            raise OrderPlacementError(data.get('retMsg'))
        
        return self.get_order(symbol_object, data['result']['orderId'])

    def get_order(self, symbol:'MarketSymbol|str', order:'Order|int', retries:int=1) -> 'Order':
        if not isinstance(order, str) and not isinstance(order, int):
            order_id = order.oid
        else:
            order_id = order
        url = f'{self.url}/v5/order/history'
        payload = {
            'category': 'spot',
            'orderId': order_id
        }
        query = self.sign(payload)
        uri = f'{url}?{query}'
        response = self.session.get(uri)
        response.raise_for_status()
        data = response.json()
        if data.get('retMsg') not in ['OK', 'success']:
            raise ValueError(data)
        try:
            order_payload = data['result']['list'][0]
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

    def get_full_orderbook(self, symbol:'MarketSymbol|str', limit:int=5000) -> dict:
        symbol_object = self.get_symbol_from_name(symbol) if isinstance(symbol, str) else symbol
        if not symbol_object:
            raise ValueError(f'Symbol not found: {symbol}')
        url = f'{self.url}/v5/market/orderbook'
        payload = {
            'category': 'spot',
            'symbol': self.format_symbol(symbol_object.name),
            'limit': limit
        }
        query = self.sign(payload)
        uri = f'{url}?{query}'
        response = self.session.get(uri)
        response.raise_for_status()
        data = response.json()
        if data.get('retMsg') not in ['OK', 'success']:
            raise ValueError(data)
        snapshot = self.format_orderbook(data['result'])
        self.orderbook_seq = data['result']['seq']
        return snapshot

    def format_orderbook(self, data:dict) -> dict:
        if (data.get('seq') or 0) <= self.orderbook_seq:
            print('Ignoring orderbook update, seq:', data['seq'], 'current:', self.orderbook_seq)
            return { 'bids': [], 'asks': [] }
        return {
            'bids': [ { 'price': Decimal(bid[0]), 'size': Decimal(bid[1]), 'count': 1 } for bid in data['b'] ],
            'asks': [ { 'price': Decimal(ask[0]), 'size': Decimal(ask[1]), 'count': 1 } for ask in data['a'] ]
        }

    def init_orderbook_websocket(self, symbol:'MarketSymbol|str', callback:typing.Callable, liveloop:'LiveLoop|LoopGroup|None'=None, retries:int=0):
        ws_uri = 'wss://stream.bybit.com/v5/public/spot'
        symbol_object = self.get_symbol_from_name(symbol) if isinstance(symbol, str) else symbol
        if not symbol_object:
            raise ValueError(f'Symbol not found: {symbol}')
        ws = connect(ws_uri)
        ws.send(json.dumps({
            'op': 'subscribe',
            'args': [f'orderbook.200.{self.format_symbol(symbol_object.name)}']
        }))
        ack = json.loads(ws.recv())
        if not ack.get('success'):
            raise MarketAPIError(f'Failed to subscribe to websocket: {ack}')
        while not self.stop_websocket_stream:
            try:
                data = json.loads(ws.recv())
                if data.get('op') == 'pong':
                    continue
            except (ConnectionClosed, ConnectionClosedOK):
                if retries < self.WS_MAX_RETRIES:
                    time.sleep(1)
                    return self.init_orderbook_websocket(symbol, callback, liveloop, retries+1)
                raise MarketAPIError('Failed to connect to websocket')
            except:
                if retries < self.WS_MAX_RETRIES:
                    time.sleep(1)
                    return self.init_orderbook_websocket(symbol, callback, liveloop, retries+1)
                raise MarketAPIError('Failed to connect to websocket')
            update = self.format_orderbook(data['data'])
            if data['data']['seq']:
                self.orderbook_seq = data['data']['seq']
            callback(update)
        ws.close()

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

    def prep_order(self, order:dict) -> 'Order':
        from quantapi.models import Order
        return Order(
            oid=order['orderId'],
            status='FILLED' if order['orderStatus'] == 'PartiallyFilledCanceled' else order['orderStatus'].upper(),
            order_type=order['orderType'].upper(),
            deal_size=float(order['cumExecQty']),
            deal_funds=float(order['cumExecValue']),
            price=float(order['basePrice']),
            side=order['side'].upper(),
            market_timestamp=self.standardize_timestamp(order['createdTime']),
            symbol=self.get_symbol_from_name(self.standardize_symbol(order['symbol'])),
            account=self.account,
            details=json.dumps(order, indent=2)
        )

    def prep_symbol(self, symbol:dict) -> 'MarketSymbol':
        from quantapi.models import MarketSymbol
        symbol_object = MarketSymbol(
            market=self.market,
            name=self.standardize_symbol(symbol['symbol']),
            base=symbol['baseCoin'],
            quote=symbol['quoteCoin'],
            base_precision=float(symbol['lotSizeFilter'].get('basePrecision', 0)),
            quote_precision=float(symbol['priceFilter'].get('quotePrecision', 0)),
            spot_trading_enabled=symbol['status'] == 'Trading',
            margin_trading_enabled=symbol['marginTrading'] != 'none',
            details=json.dumps(symbol, indent=2)
        )
        return symbol_object

    def format_symbol(self, name:str) -> str:
        return name.upper().replace('-', '')

    def standardize_symbol(self, symbol:str) -> str:
        return symbol.upper().replace('-', '').replace('USDT', '-USDT')

    def format_timestamp(self, ts:datetime) -> str:
        return str(int(ts.timestamp()) * 1000)

    def standardize_timestamp(self, ts:str) -> datetime:
        return datetime.fromtimestamp(int(ts) // 1000, tz=timezone.utc)

    def format_interval(self, interval:str) -> str:
        return {
            '1 min': '1',
            '5 min': '5',
            '15 min': '15',
            '30 min': '30',
            '1 hour': '60',
            '4 hour': '240',
            '12 hour': '720',
            '1 day': 'D',
            '1 week': 'W',
            '1 month': 'M',
        }[interval]

    def standardize_klines(self, data:list) -> list[list]:
        return [[
            self.standardize_timestamp(str(ts)),
            float(o),
            float(h),
            float(l),
            float(c),
            float(v)
        ] for ts, o, h, l, c, v, t in data]
    
    def get_symbol_from_name(self, name:str) -> 'MarketSymbol|None':
        return self.symbols.get(name)
    
    def format_ws_candle(self, payload:dict) -> dict:
        return {
            'time': self.standardize_timestamp(payload['timestamp']),
            'start': self.standardize_timestamp(payload['start']),
            'end': self.standardize_timestamp(payload['end']),
            'open': float(payload['open']),
            'high': float(payload['high']),
            'low': float(payload['low']),
            'close': float(payload['close']),
            'volume': float(payload['volume']),
            'closed': payload['confirm'],
        }

    def format_match(self, data:dict) -> dict:
        return {
            'time': self.standardize_timestamp(data['T']),
            'price': float(data['p']),
            'size': float(data['v']),
            'maker': True if data['S'] == 'Buy' else False,
        }

    def has_symbol(self, symbol: str) -> bool:
        symbol = self.standardize_symbol(symbol)
        return symbol in self.symbols or symbol.split('-')[0] in self.symbols
