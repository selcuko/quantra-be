# myapp/consumers.py
import asyncio
import json
import threading
import django

from orderpulse.dispatchers import KeeperDispatchPool
from orderpulse.structures import Delta
django.setup()
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from quantapi.models import Market, MarketSymbol


class OrderbookConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.keeper = None
        self.count = 5
        self.depth = 1
        await self.accept()
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

    def get_keeper(self, market, symbol):
        market = Market.objects.get(exchange_name=market)
        symbol = MarketSymbol.objects.get(name=symbol, market=market)
        return KeeperDispatchPool.get(symbol)

    async def subscribe(self, event):
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
        snapshot = await sync_to_async(self.keeper.keeper.snapshot)()
        payload = await sync_to_async(snapshot.json)()
        await self.send(text_data=payload)

    def callback(self, delta: Delta):
        if not self.connected:
            print('Channel name not set, cannot send message', self.close_code)
            return
        asyncio.run(self.send(text_data=delta.json()))


class CandleConsumer(AsyncWebsocketConsumer):
    def get_symbol(self):
        try:
            symbol = self.scope['url_route']['kwargs']['symbol'].upper()
            market = self.scope['url_route']['kwargs']['market'].upper()
            self.symbol = MarketSymbol.objects.get(name=symbol, market__exchange_name=market)
            self.interface = self.symbol.market.get_interface()
            return self.symbol
        except MarketSymbol.DoesNotExist:
            raise Exception(f'Symbol {symbol} not found in {market}.')
        except KeyError:
            raise Exception('Market and symbol must be specified in the URI.')

    async def connect(self):
        await self.accept()
        try:
            await sync_to_async(self.get_symbol)()
        except Exception as e:
            await self.send(text_data=json.dumps({'error': str(e)}))
            await self.close()
        threading.Thread(target=self.interface.init_match_engine, args=(self.symbol.name, '1 min', self.callback, None, None, self.callback)).start()

    async def disconnect(self, close_code):
        pass

    async def receive(self, text_data):
        pass

    def callback(self, candle: dict):
        asyncio.run(self.send(text_data=json.dumps(candle, default=str)))
