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
        self.update = {}
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
        # send ACK frame and start the subscription loop
        try:
            market = event['market']
            symbol = event['symbol']
            self.depth = event.get('depth', 1)
            self.count = event.get('count', 10)
        except KeyError:
            await self.send(text_data=json.dumps({'error': 'Market and symbol must be specified'}))
            return
        self.keeper = await sync_to_async(self.get_keeper)(market, symbol)
        if not self.keeper.is_running():
            self.keeper.start()
        await self.sub_loop()

    async def sub_loop(self):
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




class ChatConsumer(AsyncWebsocketConsumer):
    # type hinting
    async def connect(self):
        self.room_name = self.scope["url_route"]["kwargs"]["room_name"]
        self.room_group_name = f"chat_{self.room_name}"
        # Join room group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    # Receive message from WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json["message"]

        # Send message to room group
        conn_id = self.scope["client"][1]
        await self.channel_layer.group_send(self.room_group_name, {"type": "chat.message", "message": f'[{conn_id}]: {message}'})

    # Receive message from room group
    async def chat_message(self, event):
        message = event["message"]

        # Send message to WebSocket
        await self.send(text_data=json.dumps({"message": message}))