# myapp/consumers.py
import asyncio
import json
import threading
from urllib.parse import parse_qs
import django

from orderpulse.aggregator import Aggregator, AggregatorPool
from orderpulse.keeper import Keeper, KeeperPool
from orderpulse.structures import Delta
django.setup()
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from quantapi.models import Market, MarketSymbol


class OrderbookConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.connected = False
        self.keeper = None
        self.count = 5
        self.depth = 1
        query_params = parse_qs(self.scope['query_string'].decode('utf-8'))
        contract = query_params.get('contract', [None])[0]
        self.futures = True if contract == 'FUTURES' else False
        await self.accept()
        await self.subscribe({'market': self.scope['url_route']['kwargs']['market'], 'symbol': self.scope['url_route']['kwargs']['symbol']})
        self.connected = True

    async def disconnect(self, close_code):
        self.close_code = close_code
        self.connected = False
        if self.keeper and self.callback in self.keeper.callbacks:
            self.keeper.callbacks.remove(self.callback)

    async def receive(self, text_data):
        try:
            inbound = json.loads(text_data)
        except json.decoder.JSONDecodeError:
            await self.send(text_data=json.dumps({'error': 'Invalid JSON'}))
            return
        message_type = inbound.get('type')
        if not message_type:
            await self.send(text_data=json.dumps({'error': 'No message type specified'}))
            return
        handler = getattr(self, message_type, self.default_handler)
        await handler(inbound)

    async def default_handler(self, event):
        await self.send(text_data=json.dumps({'error': 'Invalid message type'}))

    def get_keeper(self, market, symbol) -> Keeper:
        market = Market.objects.get(exchange_name=market)
        symbol = MarketSymbol.objects.get(contract_type=MarketSymbol.ContractType.SPOT, name=symbol, market=market)
        return KeeperPool.get(symbol, futures=self.futures)

    async def subscribe(self, event):
        if self.connected:
            await self.send(text_data=json.dumps({'error': 'Already connected'}))
            return
        try:
            market = event['market']
            symbol = event['symbol']
            self.depth = event.get('depth', 1)
            self.count = event.get('count', 10)
        except KeyError:
            await self.send(text_data=json.dumps({'error': 'Market and symbol must be specified'}))
            return
        try:
            self.keeper = await sync_to_async(self.get_keeper)(market, symbol)
        except Market.DoesNotExist:
            await self.send(text_data=json.dumps({'error': f'Market {market} not found'}))
            return
        except MarketSymbol.DoesNotExist:
            await self.send(text_data=json.dumps({'error': f'Symbol {symbol} not found in {market}'}))
            return
        self.keeper.add_callback(self.callback)

    async def snapshot(self, event):
        if not self.keeper:
            return
        if not self.keeper:
            return
        snapshot = await sync_to_async(self.keeper.snapshot)()
        payload = await sync_to_async(snapshot.json)()
        await self.send(text_data=payload)

    def callback(self, delta: Delta):
        if not self.connected:
            print('Channel name not set, cannot send message', self.close_code)
            return
        asyncio.run(self.send(text_data=delta.json()))


class MiniOrderbookConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.connected = False
        self.keeper = None
        self.count = 5
        self.depth = 1
        query_params = parse_qs(self.scope['query_string'].decode('utf-8'))
        contract = query_params.get('contract', [None])[0]
        self.futures = True if contract == 'FUTURES' else False
        await self.accept()
        print('Connected')
        await self.subscribe({'market': self.scope['url_route']['kwargs']['market'], 'symbol': self.scope['url_route']['kwargs']['symbol']})
        print('Subscribed')
        self.connected = True

    async def disconnect(self, close_code):
        self.close_code = close_code
        self.connected = False
        if self.keeper and self.callback in self.keeper.callbacks:
            self.keeper.callbacks.remove(self.callback)

    async def receive(self, text_data):
        try:
            inbound = json.loads(text_data)
        except json.decoder.JSONDecodeError:
            await self.send(text_data=json.dumps({'error': 'Invalid JSON'}))
            return
        message_type = inbound.get('type')
        if not message_type:
            await self.send(text_data=json.dumps({'error': 'No message type specified'}))
            return
        handler = getattr(self, message_type, self.default_handler)
        await handler(inbound)

    async def default_handler(self, event):
        await self.send(text_data=json.dumps({'error': 'Invalid message type'}))

    def get_keeper(self, market, symbol) -> Keeper:
        market = Market.objects.get(exchange_name=market)
        symbol = MarketSymbol.objects.get(contract_type=MarketSymbol.ContractType.SPOT, name=symbol, market=market)
        return KeeperPool.get(symbol, futures=self.futures)

    async def subscribe(self, event):
        if self.connected:
            await self.send(text_data=json.dumps({'error': 'Already connected'}))
            return
        try:
            market = event['market']
            symbol = event['symbol']
            self.depth = event.get('depth', 1)
            self.count = event.get('count', 10)
        except KeyError:
            await self.send(text_data=json.dumps({'error': 'Market and symbol must be specified'}))
            return
        try:
            self.keeper = await sync_to_async(self.get_keeper)(market, symbol)
            self.keeper.add_callback(self.callback)
        except Market.DoesNotExist:
            await self.send(text_data=json.dumps({'error': f'Market {market} not found'}))
            return
        except MarketSymbol.DoesNotExist:
            await self.send(text_data=json.dumps({'error': f'Symbol {symbol} not found in {market}'}))
            return
        # start update loop

    def callback(self, delta: Delta):
        if self.keeper and self.connected:
            bids, asks = self.keeper.book.get_depth(self.count, self.depth)
            payload = json.dumps({
                'bids': [bid.dict() for bid in bids],
                'asks': [ask.dict() for ask in asks],
                'price': str(self.keeper.book.get_price())
            })
            if self.connected:
                asyncio.run(self.send(text_data=payload))


class AggregatorConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.connected = False
        self.aggregator = None
        self.count = 5
        self.depth = 1
        query_params = parse_qs(self.scope['query_string'].decode('utf-8'))
        contract = query_params.get('contract', [None])[0]
        self.futures = True if contract == 'FUTURES' else False
        await self.accept()
        await self.subscribe({'market': self.scope['url_route']['kwargs']['market'], 'symbol': self.scope['url_route']['kwargs']['symbol']})
        self.connected = True

    async def disconnect(self, close_code):
        self.close_code = close_code
        self.connected = False
        # if self.aggregator and self.callback in self.aggregator.callbacks:
        #     self.aggregator.callbacks.remove(self.callback)

    async def receive(self, text_data):
        try:
            inbound = json.loads(text_data)
        except json.decoder.JSONDecodeError:
            await self.send(text_data=json.dumps({'error': 'Invalid JSON'}))
            return
        message_type = inbound.get('type')
        if not message_type:
            await self.send(text_data=json.dumps({'error': 'No message type specified'}))
            return
        handler = getattr(self, message_type, self.default_handler)
        await handler(inbound)

    async def default_handler(self, event):
        await self.send(text_data=json.dumps({'error': 'Invalid message type'}))

    def get_aggregator(self, symbol, markets) -> Aggregator:
        return AggregatorPool.get(symbol, markets, futures=self.futures)

    async def subscribe(self, event):
        if self.connected:
            await self.send(text_data=json.dumps({'error': 'Already connected'}))
            return
        try:
            symbol = event['symbol']
            markets = event['markets']
            self.depth = event.get('depth', 1)
            self.count = event.get('count', 10)
        except KeyError:
            await self.send(text_data=json.dumps({'error': 'Market and symbol must be specified'}))
            return
        try:
            self.aggregator = await sync_to_async(self.get_aggregator)(symbol, markets)
            self.aggregator.add_callback(self.callback)
        except Market.DoesNotExist:
            await self.send(text_data=json.dumps({'error': f'Market {markets} not found'}))
            return
        except MarketSymbol.DoesNotExist:
            await self.send(text_data=json.dumps({'error': f'Symbol {symbol} not found in {markets}'}))
            return

    def callback(self, delta: Delta):
        if not self.connected:
            print('Channel name not set, cannot send message', self.close_code)
            return
        asyncio.run(self.send(text_data=delta.json()))


class MiniAggregatorConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.connected = False
        self.aggregator = None
        self.count = 5
        self.depth = 1
        query_params = parse_qs(self.scope['query_string'].decode('utf-8'))
        contract = query_params.get('contract', [None])[0]
        self.futures = True if contract == 'FUTURES' else False
        await self.accept()
        await self.subscribe({'markets': self.scope['url_route']['kwargs']['markets'], 'symbol': self.scope['url_route']['kwargs']['symbol']})
        self.connected = True

    async def disconnect(self, close_code):
        self.close_code = close_code
        self.connected = False
        if self.aggregator and self.callback in self.aggregator.callbacks:
            self.aggregator.callbacks.remove(self.callback)
    
    async def receive(self, text_data):
        try:
            inbound = json.loads(text_data)
        except json.decoder.JSONDecodeError:
            await self.send(text_data=json.dumps({'error': 'Invalid JSON'}))
            return
        message_type = inbound.get('type')
        if not message_type:
            await self.send(text_data=json.dumps({'error': 'No message type specified'}))
            return
        handler = getattr(self, message_type, self.default_handler)
        await handler(inbound)

    async def default_handler(self, event):
        await self.send(text_data=json.dumps({'error': 'Invalid message type'}))

    def get_aggregator(self, symbol, markets) -> Aggregator:
        return AggregatorPool.get(symbol, markets, futures=self.futures)

    async def subscribe(self, event):
        if self.connected:
            await self.send(text_data=json.dumps({'error': 'Already connected'}))
            return
        try:
            symbol = event['symbol']
            markets = event['markets'].split(',')
            self.depth = event.get('depth', 1)
            self.count = event.get('count', 10)
        except KeyError:
            await self.send(text_data=json.dumps({'error': 'Market and symbol must be specified'}))
            return
        try:
            self.aggregator = await sync_to_async(self.get_aggregator)(symbol, markets)
            self.aggregator.add_callback(self.callback)
        except Market.DoesNotExist:
            await self.send(text_data=json.dumps({'error': f'Market {markets} not found'}))
            return
        except MarketSymbol.DoesNotExist:
            await self.send(text_data=json.dumps({'error': f'Symbol {symbol} not found in {markets}'}))
            return

    def callback(self, delta: Delta):
        if self.aggregator and self.connected:
            bids, asks = self.aggregator.book.get_depth(self.count, self.depth)
            payload = json.dumps({
                'bids': [bid.dict() for bid in bids],
                'asks': [ask.dict() for ask in asks],
                'price': str(self.aggregator.book.get_price())
            })
            try:
                asyncio.run(self.send(text_data=payload))
            except Exception as e:
                self.connected = False


class CandleConsumer(AsyncWebsocketConsumer):
    def get_symbol(self):
        try:
            symbol = self.scope['url_route']['kwargs']['symbol'].upper()
            market = self.scope['url_route']['kwargs']['market'].upper()
            self.symbol = MarketSymbol.objects.get(contract_type=MarketSymbol.ContractType.SPOT, name=symbol, market__exchange_name=market)
            self.interface = self.symbol.market.get_interface()
            return self.symbol
        except MarketSymbol.DoesNotExist:
            raise Exception(f'Symbol {symbol} not found in {market}.')
        except KeyError:
            raise Exception('Market and symbol must be specified in the URI.')

    async def connect(self):
        await self.accept()
        self.connected = True
        try:
            await sync_to_async(self.get_symbol)()
        except Exception as e:
            await self.send(text_data=json.dumps({'error': str(e)}))
            await self.close()
        threading.Thread(target=self.interface.init_match_engine, args=(self.symbol.name, '1 min', self.callback, None, None, self.callback)).start()

    async def disconnect(self, close_code):
        self.connected = False

    async def receive(self, text_data):
        pass

    def callback(self, candle: dict):
        if not self.connected:
            return
        asyncio.run(self.send(text_data=json.dumps(candle, default=str)))
