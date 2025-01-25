import json
from threading import Event
import time
import typing
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal
if typing.TYPE_CHECKING:
    from quantapi.models import MarketSymbol, MarketAccount

import pytz
from kucoin.client import Market, Trade, User
from kucoin_futures.client import Market as FuturesMarket
import requests

from logger import logger
from markets import IMarket
from markets.errors import InsufficientBalance, SymbolNotInMarket
from markets.helper import authentication_required, float_to_precision
from match import MatchEngine
from models import interval_to_minutes
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK
from websockets.sync.client import ClientConnection


class KucoinMarket(IMarket):
    name = 'KuCoin'

    def __init__(self, config:dict, account:'MarketAccount|None', market:'Market|None'=None) -> None:
        if not config:
            config = {}
        self.authenticated = bool(config.get('API_KEY') and config.get('API_SECRET') and config.get('API_PASSPHRASE'))
        self.private = self.authenticated
        self.testnet = False  # KuCoin does not offer a TestNet at the moment (2023-09-22)
        self.spot_trading_enabled = False
        self.capital = 0
        self.assets = {}
        self.account = account
        self.market = self.account.market if self.account else market  # type: ignore
        self.commission = {}
        try:
            if self.authenticated:
                self.kmarket = Market(
                    key=config['API_KEY'], 
                    secret=config['API_SECRET'], 
                    passphrase=config['API_PASSPHRASE'])
                self.trade = Trade(
                    key=config['API_KEY'], 
                    secret=config['API_SECRET'], 
                    passphrase=config['API_PASSPHRASE'])
                self.user = User(
                    key=config['API_KEY'], 
                    secret=config['API_SECRET'], 
                    passphrase=config['API_PASSPHRASE'])
            else:
                self.kmarket = Market()
            self.fmarket = FuturesMarket()
        except:
            logger.fatal(f'Error while initializing {self.name}', exc_info=True)
            raise

        self.symbols = self.get_symbols()

        if self.authenticated:
            self.get_account()
        self.get_symbols()

        self.stop_websocket_stream = False

    def get_websocket_token(self) -> str:
        uri = 'https://api.kucoin.com/api/v1/bullet-public'
        response = requests.post(uri)
        if response.status_code != 200:
            raise ValueError(f'Error while getting websocket token for {self.name}: {response.status_code} {response.text}')
        token = response.json().get('data', {}).get('token')
        if not token:
            raise ValueError(f'Error while getting websocket token for {self.name}: {response.json()}')
        return token

    def format_ws_candle(self, candle:dict) -> dict:      
        return {
            'time': candle['start'].astimezone(pytz.UTC),
            'start': candle['start'].astimezone(pytz.UTC),
            'end': candle['end'].astimezone(pytz.UTC),
            'open': float(candle['open']),
            'high': float(candle['high']),
            'low': float(candle['low']),
            'close': float(candle['close']),
        }

    def init_websocket(self, symbol:str, interval:str, callback:typing.Callable):
        token = self.get_websocket_token()
        conn_id = uuid.uuid4().hex
        ws_uri = f'wss://ws-api-spot.kucoin.com/?token={token}&[connectId={conn_id}]'
        interval_m = interval_to_minutes(interval)
        ws = connect(ws_uri)
        welcome = ws.recv()
        if not json.loads(welcome)['type'] == 'welcome':
            raise ValueError(f'Error while initializing websocket for {self.name}: {welcome}')
        sub = {
            "id": str(uuid.uuid4()),
            "type": "subscribe",
            "topic": f'/market/ticker:{symbol}',
            "privateChannel": False,
            "response": True 
        }
        ws.send(json.dumps(sub))
        ack = json.loads(ws.recv())
        if not ack.get('type') == 'ack':
            raise ValueError(f'Error while subscribing to {symbol} on {self.name}: {ack}')
        candle_interval = timedelta(minutes=interval_m)
        current_candle_start = datetime.now().replace(second=0, microsecond=0)
        current_candle_start -= timedelta(minutes=current_candle_start.minute % interval_m)
        current_candle = None
        last_ping = datetime.now()
        while not self.stop_websocket_stream:
            if last_ping < datetime.now() - timedelta(seconds=30):
                ws.send(json.dumps({'id': str(uuid.uuid4()), 'type': 'ping'}))
                last_ping = datetime.now()
            try:
                msg = json.loads(ws.recv(timeout=10))
            except TimeoutError:
                continue
            if msg.get('type') == 'pong':
                continue
            ts = msg.get('data', {}).get('time')
            dt = datetime.utcfromtimestamp(ts / 1000)
            if current_candle is None:
                current_candle = {
                    'start': current_candle_start,
                    'end': current_candle_start + candle_interval,
                    'open': None,
                    'high': None,
                    'low': None,
                    'close': None
                }
            if dt >= current_candle['end']:
                current_candle = self.format_ws_candle(current_candle)
                callback(current_candle)
                current_candle_start += candle_interval
                current_candle['start'] = current_candle_start
                current_candle['end'] = current_candle_start + candle_interval
                current_candle['open'] = None
                current_candle['high'] = None
                current_candle['low'] = None
                current_candle['close'] = None
            price = msg.get('data', {}).get('price')
            if current_candle['open'] is None and price != 0:
                current_candle['open'] = price
            if current_candle['high'] is None or price > current_candle['high']:
                current_candle['high'] = price
            if current_candle['low'] is None or price < current_candle['low']:
                current_candle['low'] = price
            if price != 0:
                current_candle['close'] = price

    def format_match(self, data):
        spot_t = int(data.get('time', 0))
        futures_t = int(data.get('ts', 0))
        return {
            'time': datetime.fromtimestamp(max(spot_t, futures_t) / 1000000000, pytz.UTC),
            'price': float(data['price']),
            'size': float(data['size']),
            'maker': data['side'] == 'buy',
        }

    def format_topic_match(self, symbol:'MarketSymbol') -> str:
        mapping = {
            'SPOT': f'/market/match:{symbol.name}',
            'FUTURES': f'/contractMarket/execution:{symbol.name.split("-")[0]}USDTM',
        }
        return mapping.get(symbol.contract_type, '')

    def get_match_engine_socket(self, symbol:'MarketSymbol|str') -> ClientConnection:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)

        token = self.get_websocket_token()
        conn_id = uuid.uuid4().hex
        ws_uri = f'wss://ws-api-spot.kucoin.com/?token={token}&[connectId={conn_id}]'
        ws = connect(ws_uri)
        welcome = ws.recv()
        sub = {
            "id": str(uuid.uuid4()),
            "type": "subscribe",
            "topic": self.format_topic_match(symbol),
            "privateChannel": False,
            "response": True 
        }
        ws.send(json.dumps(sub))
        ack = json.loads(ws.recv())
        if not ack.get('type') == 'ack':
            raise ValueError(f'Error while subscribing to {symbol} on {self.name}: {ack}')
        return ws

    def init_match_engine(self, symbol:'MarketSymbol', interval:str, callback:typing.Callable, stop_event:Event, raw_callback=None, ticker_callback=None):
        ws = self.get_match_engine_socket(symbol)
        last_ping = datetime.now()
        engine = MatchEngine(symbol, interval, callback, ticker_callback)
        retries = 0

        while not stop_event.is_set():
            if last_ping < datetime.now() - timedelta(seconds=30):
                ws.send(json.dumps({'id': str(uuid.uuid4()), 'type': 'ping'}))
                last_ping = datetime.now()
            try:
                data = json.loads(ws.recv(timeout=10))
                retries = 0
            except TimeoutError:
                continue
            except (ConnectionClosed, ConnectionClosedOK):
                ws = self.get_match_engine_socket(symbol)
                continue
            except:
                if retries > self.WS_MAX_RETRIES:
                    logger.error(f'Error while initializing match engine for {symbol} on {self.name}', exc_info=True)
                    raise
                retries += 1
                ws = self.get_match_engine_socket(symbol)
                continue
            if data.get('type') == 'pong':
                continue
            if data.get('subject') not in ['trade.l3match', 'match']:
                continue
            if raw_callback:
                raw_callback(data)
            engine.on_match(self.format_match(data.get('data')))

    def has_symbol(self, symbol:str) -> bool:
        if not self.symbols:
            self.symbols = self.get_symbols()
        return symbol in self.symbols

    def _standardize_klines(self, klines:list) -> list[list]:
        try:
            klines.reverse()
            return [[
                self._standardize_datetime(kline[0]),
                float(kline[1]),
                float(kline[3]),
                float(kline[4]),
                float(kline[2]),
                float(kline[5]),
            ] for kline in klines ]
        except:
            logger.error(f'Error while standardizing klines for {self.name}: {klines}', exc_info=True)
            raise

    def _standardize_futures_klines(self, klines:list) -> list[list]:
        try:
            return [[
                self._standardize_datetime(kline[0]),
                float(kline[1]),
                float(kline[3]),
                float(kline[4]),
                float(kline[2]),
                float(kline[5]),
            ] for kline in klines ]
        except:
            logger.error(f'Error while standardizing klines for {self.name}: {klines}', exc_info=True)
            raise

    @staticmethod
    def _standardize_symbol(symbol:str) -> str:
        return symbol

    @staticmethod
    def _standardize_future_symbol(symbol:dict) -> str:
        return symbol.get('baseCurrency','') + '-' + symbol.get('quoteCurrency','')

    def _standardize_datetime(self, dt:int|str) -> "datetime|None":
        try:
            return datetime.fromtimestamp(int(dt), tz=pytz.UTC)
        except ValueError:
            return datetime.fromtimestamp(int(dt)/1000, tz=pytz.UTC)
        except:
            logger.error(f'Error while standardizing datetime for {self.name}: {dt}', exc_info=True)

    @staticmethod
    def _format_symbol(symbol:str) -> str:
        return symbol.upper()

    @staticmethod
    def _format_interval(interval:str) -> str:
        return interval.replace(' ', '')

    @staticmethod
    def _format_datetime(dt:datetime) -> int:
        assert isinstance(dt, datetime), f'Expected datetime, got {type(dt)}'
        return int(dt.timestamp())

    def _get_symbol_from_name(self, symbol_name:str):
        try:
            return self.symbols[symbol_name]
        except KeyError:
            logger.error(f'Symbol {symbol_name} is not present in {self.name}')
            raise ValueError(f'Symbol {symbol_name} is not present in {self.name}')

    def _prep_symbol(self, symbol:dict) -> 'MarketSymbol':
        from quantapi.models import MarketSymbol
        return MarketSymbol(
            market=self.market,
            name=self._standardize_symbol(symbol['symbol']),
            base=symbol['baseCurrency'],
            quote=symbol['quoteCurrency'],
            base_precision=symbol['baseIncrement'],
            quote_precision=symbol['quoteIncrement'],
            spot_trading_enabled=symbol['enableTrading'],
            margin_trading_enabled=symbol['isMarginEnabled'],
            details=json.dumps(symbol),
            contract_type=MarketSymbol.ContractType.SPOT
            )

    def _prep_future_symbol(self, symbol:dict) -> 'MarketSymbol':
        from quantapi.models import MarketSymbol
        return MarketSymbol(
            market=self.market,
            name=self._standardize_future_symbol(symbol),
            base=symbol['baseCurrency'],
            quote=symbol['quoteCurrency'],
            details=json.dumps(symbol),
            contract_type=MarketSymbol.ContractType.FUTURES,
            )

    def _prep_order(self, order:dict) -> 'Order':
        from quantapi.models import Order
        oid = order.get('orderId') or order.get('id')
        return Order(
            oid=oid,
            order_type=order.get('type', 'unknown').upper(),
            price=float(order.get('price', 0)),
            market_timestamp=self._standardize_datetime(str(order.get('createdAt'))) if order.get('createdAt') else None,
            deal_funds=float(order.get('dealFunds', 0)),
            deal_size=float(order.get('dealSize', 0)),
            status='NEW' if order.get('isActive') else 'FILLED',
            funds=float(order.get('funds', 0)),
            client_oid=order.get('clientOid'),
            details=json.dumps(order),
        )

    def _get_klines(self, symbol:'str|MarketSymbol', interval:str, start:datetime, end:"datetime|None"=None, limit=1000, retry=0) -> list[list]:
        if isinstance(symbol, str):
            contract_type = MarketSymbol.ContractType.SPOT
        else:
            contract_type = getattr(symbol, 'contract_type')
            symbol = symbol.name
        if not self.has_symbol(symbol):
            raise SymbolNotInMarket(f'Symbol {symbol} is not available in {self.name}')
        if end:
            calculated_end = end
        else:
            calculated_end = start + timedelta(minutes=interval_to_minutes(interval) * limit)
        try:
            if contract_type == 'SPOT':
                # Max limit for spot is 1500
                klines = self.kmarket.get_kline(
                    symbol=self._format_symbol(symbol),
                    kline_type=self._format_interval(interval),
                    startAt=self._format_datetime(start),
                    endAt=self._format_datetime(calculated_end),
                    limit=limit)
            elif contract_type == 'FUTURES':
                # Max limit for futures is 500
                symbol = self._format_symbol(symbol)
                klines = self.fmarket.get_kline_data(
                    symbol=symbol.split('-')[0] + symbol.split('-')[1]+'M',
                    granularity=interval_to_minutes(interval),
                    begin_t=int(self._format_datetime(start) * 1000),
                    end_t=int(self._format_datetime(calculated_end) * 1000))
        except:
            logger.error(f'Error fetching klines for {self._format_symbol(symbol)} from {self.name}', exc_info=True)
            if retry > 0:
                logger.warning(f'Retrying {retry} more times')
                time.sleep(1)
                return self._get_klines(symbol, interval, start, end, limit, retry-1)
            return []
        if not klines or not isinstance(klines, list) or not isinstance(klines[0], list):
            return []
        return self._standardize_klines(klines) if contract_type == 'SPOT' else self._standardize_futures_klines(klines)

    def get_klines(self, symbol:'str|MarketSymbol', interval:str, start:"datetime", end:"datetime|None"=None, limit=1000, retry=0) -> list[list]:
        return self._get_klines(symbol, interval, start, end, limit, retry)

    def get_last_klines(self, symbol:'str|MarketSymbol', interval:str, limit=100, retry=1, silent=True) -> list[list]:
        minutes = interval_to_minutes(interval)
        now = datetime.now(tz=pytz.UTC)
        start = now - timedelta(minutes=minutes*limit)
        klines = self.get_klines(symbol, interval, start, now, limit=limit*2)
        if not klines:
            return []
        last_kline_dt = klines[-1][0]
        if (now - last_kline_dt) > timedelta(minutes=minutes*2):
            error = f'Last kline dt {last_kline_dt} does not match current time {now}, total klines: {len(klines)}, {start} -> {now}'
            logger.warning(error)
            if retry > 0:
                return self.get_last_klines(symbol, interval, limit, retry-1)
            if not silent:
                raise ValueError(error)
        return klines

    def get_future_symbols(self) -> dict[str, 'MarketSymbol']:
        from quantapi.models import MarketSymbol
        symbol_list = self.fmarket.get_contracts_list()
        with open('kucoin_futures.json', 'w') as f:
            json.dump(symbol_list, f)
        if not symbol_list:
            logger.error(f'No symbols found on {self.name}')
            return {}
        self.futures_symbols = { self._standardize_future_symbol(symbol) + '.F': self._prep_future_symbol(symbol) for symbol in symbol_list }
        self.futures_symbols = { key: value for key, value in self.futures_symbols.items() if value.quote == 'USDT'}
        MarketSymbol.objects.bulk_create(self.futures_symbols.values(), update_conflicts=True, update_fields=[
                'details',
            ], unique_fields=['name', 'market', 'contract_type'])
        MarketSymbol.objects.filter(market=self.market, contract_type=MarketSymbol.ContractType.FUTURES).exclude(name__in=[symbol.name for symbol in self.symbols.values()]).delete()
        return self.futures_symbols

    def get_symbols(self) -> dict[str, 'MarketSymbol']:
        from quantapi.models import MarketSymbol
        symbol_list = self.kmarket.get_symbol_list_v2()
        if not symbol_list:
            logger.error(f'No symbols found on {self.name}')
            return {}
        self.symbols = { self._standardize_symbol(symbol['symbol']): self._prep_symbol(symbol) for symbol in symbol_list }
        self.symbols = { key: value for key, value in self.symbols.items() if value.quote == 'USDT'}
        MarketSymbol.objects.bulk_create(self.symbols.values(), update_conflicts=True, update_fields=[
                'spot_trading_enabled', 
                'margin_trading_enabled', 
                'details',
                'base_precision',
                'quote_precision',
            ], unique_fields=['name', 'market', 'contract_type'])
        MarketSymbol.objects.filter(market=self.market, contract_type=MarketSymbol.ContractType.SPOT).exclude(name__in=[symbol.name for symbol in self.symbols.values()]).delete()
        self.futures_symbols = self.get_future_symbols()
        return self.symbols

    @authentication_required
    def place_market_order(self, symbol:'MarketSymbol|str', side:Literal['buy', 'sell'], funds:"str|None"=None, quantity:"str|None"=None, validate=True) -> 'Order':
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        client_oid = uuid.uuid4().hex
        if (not funds and not quantity) or (funds and quantity):
            raise ValueError(f'You must provide either funds or quantity to place a market order on {self.name}')
        try:
            if not self.trade:
                raise ValueError(f'Cannot place market order on {self.name} without authenticated API config')
            order = self.trade.create_market_order(
                symbol=symbol.name,
                side=side,
                funds=funds,
                size=quantity,
                client_oid=client_oid)
            if not order:
                raise ValueError(f'Error while placing market order on {self.name}')
            logger.info(f'Market order placed on {self.name} for {symbol} with side {side} and funds {funds} and quantity {quantity} with order id {order["orderId"]}')
            order = self._prep_order(order)
            if not order.oid:
                raise ValueError(f'Error while placing market order on {self.name}')
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
                raise InsufficientBalance(f'Balance insufficient for market order on {self.name}') from e
            logger.error(f'Error while placing market order on {self.name}', exc_info=True)
            raise

    @authentication_required
    def place_limit_order(self, symbol:'MarketSymbol|str', side:Literal['buy', 'sell'], price:float, quantity:float, validate=True) -> 'Order':
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        client_oid = uuid.uuid4().hex
        if symbol.quote_precision:
            price = float_to_precision(Decimal(price), symbol.quote_precision)
        if symbol.base_precision:
            quantity = float_to_precision(Decimal(quantity), symbol.base_precision)
        try:
            if not self.trade:
                raise ValueError(f'Cannot place limit order on {self.name} without authenticated API config')
            order = self.trade.create_limit_order(
                symbol=symbol.name,
                side=side,
                price=price,
                size=quantity,
                client_oid=client_oid,
            )
            if not order:
                raise ValueError(f'Error while placing limit order on {self.name}')
            logger.info(f'Limit order placed on {self.name} for {symbol} with side {side} and price {price} and size {quantity} with order id {order["orderId"]}')
            order = self._prep_order(order)
            if not order.oid:
                raise ValueError(f'Error while placing limit order on {self.name}')
            if validate:
                order = self.get_order(symbol, order.oid)
            return order
        except:
            logger.error(f'Error while placing limit order on {self.name}', exc_info=True)
            raise

    @authentication_required
    def get_order(self, symbol:'MarketSymbol|str', order:'Order|str') -> 'Order':
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        from quantapi.models import Order
        if isinstance(order, Order):
            if not order.oid:
                raise ValueError('Cannot get order without oid')
            order = order.oid
        try:
            if not self.trade:
                raise ValueError(f'Cannot get order on {self.name} without authenticated API config')
            _order = self.trade.get_order_details(orderId=order)
            if not _order:
                raise ValueError(f'Error while getting order {order} on {self.name}')
            return self._prep_order(_order)
        except:
            logger.error(f'Error while getting order {order} on {self.name}', exc_info=True)
            raise

    @authentication_required
    def get_orders(self, symbol:'MarketSymbol|str') -> list['Order']:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        try:
            if not self.trade:
                raise ValueError(f'Cannot get orders on {self.name} without authenticated API config')
            orders = self.trade.get_order_list(symbol=symbol.name)
            if not orders:
                raise ValueError(f'Error while getting orders on {self.name}')
            return [self._prep_order(order) for order in orders['items']]
        except:
            logger.error(f'Error while getting orders on {self.name}', exc_info=True)
            raise

    @authentication_required
    def get_open_orders(self, symbol:'MarketSymbol|str') -> list['Order']:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        try:
            if not self.trade:
                raise ValueError(f'Cannot get open orders on {self.name} without authenticated API config')
            if symbol:
                orders = self.trade.get_order_list(symbol=symbol.name, status='active')
            else:
                orders = self.trade.get_order_list(status='active')
            if not orders:
                raise ValueError(f'Error while getting open orders on {self.name}')
            return [self._prep_order(order) for order in orders['items']]
        except:
            logger.error(f'Error while getting open orders on {self.name}', exc_info=True)
            raise

    @authentication_required
    def cancel_order(self, symbol:'MarketSymbol|str', order:'Order|str') -> 'Order':
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        if isinstance(order, Order):
            _order_oid = order.oid
        else:
            _order_oid = order
        try:
            if not self.trade:
                raise ValueError(f'Cannot cancel order on {self.name} without authenticated API config')
            _order_payload = self.trade.cancel_order(orderId=_order_oid)
            if not _order_payload:
                raise ValueError(f'Error while cancelling order {order} on {self.name}')
            return self._prep_order(_order_payload)
        except:
            logger.error(f'Error while cancelling order {order} on {self.name}', exc_info=True)
            raise

    @authentication_required
    def cancel_all_orders(self, symbol:'MarketSymbol|str') -> list['Order']:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        try:
            if not self.trade:
                raise ValueError(f'Cannot cancel all orders on {self.name} without authenticated API config')
            if symbol:
                orders = self.trade.cancel_all_orders(symbol=symbol.name)
            else:
                orders = self.trade.cancel_all_orders()
            if not orders:
                raise ValueError(f'Error while cancelling all orders on {self.name}')
            return [self._prep_order(order) for order in orders['cancelledOrderIds']]
        except:
            logger.error(f'Error while cancelling all orders on {self.name}', exc_info=True)
            raise

    def get_full_orderbook(self, symbol:'MarketSymbol|str') -> dict:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        try:
            if symbol.contract_type == symbol.ContractType.SPOT:
                if self.private:
                    orderbook = self.kmarket.get_aggregated_orderv3(symbol.name)
                else:
                    orderbook = self.kmarket.get_part_order(100, symbol.name)
            elif symbol.contract_type == symbol.ContractType.FUTURES:
                orderbook = self.fmarket.l2_order_book(symbol.name.split('-')[0] + symbol.name.split('-')[1]+'M')
            else:
                raise ValueError(f'Unknown contract type for symbol {symbol.name}')
            if not orderbook:
                raise ValueError(f'Error while getting full orderbook for {symbol} on {self.name}')
            return self.format_orderbook_snapshot(orderbook)
        except:
            logger.error(f'Error while getting full orderbook for {symbol} on {self.name}', exc_info=True)
            raise

    def format_orderbook_snapshot(self, orderbook):
        return {
            'bids': [ { 'price': Decimal(bid[0]), 'size': Decimal(bid[1]), 'count': 1 } for bid in orderbook['bids'] ],
            'asks': [ { 'price': Decimal(ask[0]), 'size': Decimal(ask[1]), 'count': 1 } for ask in orderbook['asks'] ],
        }

    def format_orderbook_update(self, update, seq):
        return {
            'bids': [ { 'price': Decimal(bid[0]), 'size': Decimal(bid[1]), 'count': 1 } for bid in update['bids'] if int(bid[2]) > seq],
            'asks': [ { 'price': Decimal(ask[0]), 'size': Decimal(ask[1]), 'count': 1 } for ask in update['asks'] if int(ask[2]) > seq],
        }

    def format_futures_orderbook_update(self, update):
        price, side, size = update['change'].split(',')
        if side == 'buy':
            return {
                'bids': [ { 'price': Decimal(price), 'size': Decimal(size), 'count': 1 } ],
                'asks': [],
            }
        else:
            return {
                'bids': [],
                'asks': [ { 'price': Decimal(price), 'size': Decimal(size), 'count': 1 } ],
            }

    def _format_topic(self, symbol:'MarketSymbol') -> str:
        mapping = {
            'SPOT': f'/market/level2:{symbol.name}',
            'FUTURES': f'/contractMarket/level2:{symbol.name.split("-")[0]}USDTM',
        }
        return mapping.get(symbol.contract_type, '')

    def init_orderbook_websocket(self, symbol:'MarketSymbol|str', callback:typing.Callable):
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        token = self.get_websocket_token()
        conn_id = uuid.uuid4().hex
        ws_uri = f'wss://ws-api-spot.kucoin.com/?token={token}&[connectId={conn_id}]'

        try:
            ws = connect(ws_uri)
        except TimeoutError:
            time.sleep(5)
            return self.init_orderbook_websocket(symbol, callback)
        welcome = ws.recv()
        if not json.loads(welcome)['type'] == 'welcome':
            raise ValueError(f'Error while initializing websocket for {self.name}: {welcome}')
        sub = {
            "id": str(uuid.uuid4()),
            "type": "subscribe",
            "topic": self._format_topic(symbol),
            "privateChannel": False,
            "response": True 
        }
        ws.send(json.dumps(sub))
        ack = json.loads(ws.recv())
        if not ack.get('type') == 'ack':
            ws.close()
            raise ValueError(f'Error while subscribing to {symbol} on {self.name}: {ack}')
        last_ping = datetime.now()
        seq = 0
        while not self.stop_websocket_stream:
            try:
                if last_ping < datetime.now() - timedelta(seconds=30):
                    ws.send(json.dumps({'id': str(uuid.uuid4()), 'type': 'ping'}))
                    last_ping = datetime.now()
                msg = json.loads(ws.recv(timeout=10))
            except TimeoutError:
                continue
            except ConnectionClosed:
                return self.init_orderbook_websocket(symbol, callback)
            if msg.get('type') == 'pong':
                continue
            if msg.get('subject') not in ['trade.l2update', 'level2']:
                continue
            if symbol.contract_type == symbol.ContractType.SPOT:
                orderbook = self.format_orderbook_update(msg['data']['changes'], seq=seq) 
            elif symbol.contract_type == symbol.ContractType.FUTURES:
                orderbook = self.format_futures_orderbook_update(msg['data'])
            callback(orderbook)
            if symbol.contract_type == symbol.ContractType.SPOT:
                seq = msg['data']['sequenceEnd']
            elif symbol.contract_type == symbol.ContractType.FUTURES:
                seq = 0
        ws.close()

    @authentication_required
    def get_account(self):
        if not self.user:
            raise ValueError(f'Cannot get account on {self.name} without authenticated API config')
        account = self.user.get_account_list(account_type='trade')
        if not account:
            logger.error(f'No account found on {self.name}')
            return
        self.spot_trading_enabled = len(account) > 0
        self.assets = { str(asset['currency']): float(asset['available']) for asset in account }
        self.capital = self.assets.get('USDT', 0)
        fees = self.user.get_base_fee()
        if not fees:
            logger.error(f'No fees found for account on {self.name}')
        else:
            self.commission = {
                'maker': float(fees['makerFeeRate']),
                'taker': float(fees['takerFeeRate']),
                'buyer': float(fees['takerFeeRate']),   # market orders count as taker
                'seller': float(fees['takerFeeRate']),  # market orders count as taker
            }
        if not self.spot_trading_enabled:
            logger.error(f'No assets found for account, spot trading disabled on {self.name}')
        if not self.capital:
            logger.error(f'No capital (USDT) found for account on {self.name}')

    def get_current_prices(self, save=True) -> dict:
        all_tickers = self.kmarket.get_all_tickers()
        if not all_tickers:
            return {}
        prices = { self._standardize_symbol(ticker['symbol']): float(ticker['last']) for ticker in all_tickers['ticker'] if ticker['symbol'].endswith('USDT') and ticker['last'] }
        if self.market and self.market.prices != prices:
            self.market.prices = json.dumps(prices)
            self.market.prices_updated = datetime.now(tz=pytz.UTC)
            if save:
                self.market.save()
        return prices

    @authentication_required
    def get_equity(self, save=True) -> float:
        prices = self.get_current_prices(save=False)
        equity = self.capital + sum([ self.assets.get(asset, 0) * prices.get(asset+'-USDT', 0) for asset in self.assets ])
        if self.account and self.account.equity != equity:
            self.account.equity = equity
            if save:
                self.account.save()
        return equity

    def orderbook_snapshot(self, symbol:'MarketSymbol|str'):
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        return self.kmarket.get_aggregated_orderv3(symbol.name)
