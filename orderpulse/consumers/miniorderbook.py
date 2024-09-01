from concurrent.futures import ThreadPoolExecutor
import django
django.setup()
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
from urllib.parse import parse_qs
import json
from quantapi.models import Market, MarketSymbol
from orderpulse.keeper import KeeperPool, Keeper
from orderpulse.structures import Delta
from orderpulse.errors import MaxPoolSizeExceeded
from asgiref.sync import sync_to_async, async_to_sync
import asyncio


holder = {}


class MiniOrderbookConsumer(AsyncWebsocketConsumer):
    DEFAULT_DEPTH = 1
    DEFAULT_COUNT = 10

    async def connect(self):
        self.group_name: str|None = None
        self.connected = False
        self.keeper: Keeper|None = None

        query_params = parse_qs(self.scope['query_string'].decode('utf-8'))
        self.contract = query_params.get('contract', ['SPOT'])[0]
        self.depth    = query_params.get('depth', [self.DEFAULT_DEPTH])[0]
        self.count    = query_params.get('count', [self.DEFAULT_COUNT])[0]
        self.connection_id = str(self.channel_name)
        self.market   = self.scope['url_route']['kwargs']['market']
        self.symbol   = self.scope['url_route']['kwargs']['symbol']

        await self.accept()
        await self.subscribe({
            'market': self.market, 
            'symbol': self.symbol,
            'depth': self.depth,
            'count': self.count
        })
        self.connected = True

    async def disconnect(self, close_code):
        await self.remove_from_group()
        self.connected = False
        if self.keeper:
            KeeperPool.release(self.keeper, seeker=self.connection_id)
        if self.keeper and self.universal_callback in self.keeper.callbacks:
            self.keeper.callbacks.remove(self.universal_callback)

    def get_keeper(self, market, symbol) -> Keeper:
        market = Market.objects.get(exchange_name=market)
        symbol = MarketSymbol.objects.get(contract_type=self.contract, name=symbol, market=market)
        return KeeperPool.get(symbol, seeker=self.connection_id)

    async def add_to_group(self):
        assert self.channel_layer, "Channel layer is not found"
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        print('added to group, new size', len(self.channel_layer.groups[self.group_name]))

    async def remove_from_group(self):
        assert self.channel_layer, "Channel layer is not found"
        if self.group_name:
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def subscribe(self, event):
        if self.connected:
            await self.send(text_data=json.dumps({ 'error': 'Already connected', 'code': 400 }))
            return
        try:
            market = event['market']
            symbol = event['symbol']
            self.depth = event.get('depth', 1)
            self.count = event.get('count', 10)
        except KeyError:
            await self.send(text_data=json.dumps({ 'error': 'Market and symbol must be specified', 'code': 400 }))
            return
        try:
            self.keeper = await sync_to_async(self.get_keeper)(market, symbol)
            self.group_name = f'keeper.{self.keeper.key}'
            await self.add_to_group()
            self.keeper.add_callback(self.universal_callback)
        except Market.DoesNotExist:
            await self.send(text_data=json.dumps({ 'error': f'Market {market} not found', 'code': 404 }))
            return
        except MarketSymbol.DoesNotExist:
            await self.send(text_data=json.dumps({ 'error': f'Symbol {symbol} not found in {market}-{self.contract}', 'code': 404 }))
            return
        except MaxPoolSizeExceeded as e:
            await self.send(text_data=json.dumps({ 'error': f'Maximum available connections are exceeded.', 'code': 503 }))
            return

    @staticmethod
    def universal_callback(delta: Delta, group_name: str, bids: list, asks: list, price: str):
        payload = {
            'bids': [bid.dict() for bid in bids],
            'asks': [ask.dict() for ask in asks],
            'price': price,
            'type': 'update',
            'time': str(delta.received)
        }
        channel_layer = get_channel_layer()
        assert channel_layer, "Channel layer is not found"
        async_to_sync(channel_layer.group_send)(group_name, payload)

    def keeper_callback(self, delta: Delta):
        if not self.keeper:
            print('Keeper not found in keeper_callback')
            return
        

    async def update(self, payload: dict):
        await self.send(text_data=json.dumps(payload))

