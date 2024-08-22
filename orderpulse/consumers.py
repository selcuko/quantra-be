# myapp/consumers.py
import asyncio
import json
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

    async def disconnect(self, close_code):
        pass

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

    def callback(self, delta: Delta):
        asyncio.run(self.send(text_data=delta.json()))
