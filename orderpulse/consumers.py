# myapp/consumers.py
import asyncio
import datetime
import json
import django
django.setup()
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from orderpulse.keeper import KeeperPool
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
        inbound = json.loads(text_data)
        message_type = inbound.get('type')
        if not message_type:
            await self.send(text_data=json.dumps({'error': 'No message type specified'}))
            return
        if not self.channel_layer:
            await self.send(text_data=json.dumps({'error': 'No channel layer'}))
            return
        handler = getattr(self, message_type, self.default_handler)
        await handler(inbound)

    async def default_handler(self, event):
        await self.send(text_data=json.dumps(event))

    def get_keeper(self, market, symbol):
        market = Market.objects.get(exchange_name=market)
        symbol = MarketSymbol.objects.get(name=symbol, market=market)
        return KeeperPool.get(symbol)

    async def subscribe(self, event):
        try:
            market = event['market']
            symbol = event['symbol']
            self.depth = event.get('depth', 1)
            self.count = event.get('count', 10)
        except KeyError:
            await self.send(text_data=json.dumps({'error': 'Market and symbol must be specified'}))
            return
        self.keeper = await sync_to_async(KeeperPool.get)(market, symbol)
        await self.sub_loop()

    async def sub_loop(self):
        if not self.keeper:
            raise ValueError('No keeper')
        while True:
            bids, asks = self.keeper.book.get_depth(count=self.count, depth=self.depth)
            await self.send(text_data=json.dumps({
                'bids': bids,
                'asks': asks,
                'price': self.keeper.book.get_price(),
            }, default=str))
            # sleep until the next second
            ms = datetime.datetime.now().microsecond
            await asyncio.sleep(1 - ms / 1_000_000)
