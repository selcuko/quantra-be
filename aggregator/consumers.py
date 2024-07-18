# myapp/consumers.py
import asyncio
import datetime
import json
import channels.layers
import django
django.setup()
from channels.generic.websocket import AsyncWebsocketConsumer, WebsocketConsumer
from asgiref.sync import sync_to_async
from orderpulse.keeper import BookKeeper
from quantapi.models import Market, MarketAccount, MarketSymbol


class OrderbookConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.keeper = None
        self.update = None
        await self.accept()

    async def disconnect(self, close_code):
        print('Disconnected:', close_code)

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
        print('Default handler:', event)
        await self.send(text_data=json.dumps(event))

    def set_update(self, update):
        self.update = update

    def get_keeper(self):
        market = Market.objects.get(exchange_name='BYBIT')
        symbol = MarketSymbol.objects.get(name='BTC-USDT', market=market)
        account = MarketAccount.objects.get(market=market)
        return BookKeeper(symbol, account, self.set_update)

    async def subscribe(self, event):
        # send ACK frame and start the subscription loop

        self.keeper = await sync_to_async(self.get_keeper)()
        self.keeper.start()
        await self.send(text_data=json.dumps({'type': 'subscribed'}))
        await self.sub_loop(event)

    async def sub_loop(self, event):
        while True:
            await self.send(text_data=json.dumps({'update': self.update}, default=str))
            await asyncio.sleep(1)




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