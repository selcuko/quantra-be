import django

from orderpulse.dispatchers import KeeperDispatch
django.setup()
from channels.generic.websocket import AsyncWebsocketConsumer
from urllib.parse import parse_qs
import json
from quantapi.models import Market, MarketSymbol
from orderpulse.keeper import Keeper
from orderpulse.errors import MaxPoolSizeExceeded
from asgiref.sync import sync_to_async


class MiniOrderbookConsumer(AsyncWebsocketConsumer):
    DEFAULT_DEPTH = 0.001
    DEFAULT_COUNT = 100
    dispatcher = KeeperDispatch()

    async def connect(self):
        self.group_name: str|None = None
        self.connected = False
        self.keeper: Keeper|None = None

        query_params = parse_qs(self.scope['query_string'].decode('utf-8'))
        self.contract = query_params.get('contract', ['SPOT'])[0]
        self.depth    = query_params.get('depth', [self.DEFAULT_DEPTH])[0]
        self.connection_id = str(self.channel_name)
        self.market   = self.scope['url_route']['kwargs']['market']
        self.symbol   = self.scope['url_route']['kwargs']['symbol']
        self.range_bids_min, self.range_bids_max = 0, self.DEFAULT_COUNT
        self.range_asks_min, self.range_asks_max = 0, self.DEFAULT_COUNT
        await self.accept()
        await self.subscribe({
            'market': self.market, 
            'symbol': self.symbol,
            'depth': self.depth,
        })
        self.connected = True

    async def disconnect(self, close_code):
        await sync_to_async(self.dispatcher.drop, thread_sensitive=False)(self.connection_id, self.keeper)

    def get_keeper(self, market, symbol) -> Keeper:
        assert self.connection_id, 'Connection ID is not available'
        market = Market.objects.get(exchange_name=market)
        symbol = MarketSymbol.objects.get(contract_type=self.contract, name=symbol, market=market)
        keeper = self.dispatcher.get(self.connection_id, symbol)
        return keeper

    async def subscribe(self, event):
        assert self.channel_layer, 'Channel layer is not available'
        if self.connected:
            await self.send(text_data=json.dumps({ 'error': 'Already connected', 'code': 400 }))
            return
        market = event['market']
        symbol = event['symbol']
        try:
            self.keeper = await sync_to_async(self.get_keeper)(market, symbol)
            self.group_name = f'{self.keeper.key}_default'
            await self.channel_layer.group_add(self.group_name, self.channel_name)
        except Market.DoesNotExist:
            await self.send(text_data=json.dumps({ 'error': f'Market {market} not found', 'code': 404 }))
            await self.close()
        except MarketSymbol.DoesNotExist:
            await self.send(text_data=json.dumps({ 'error': f'Symbol {symbol} not found in {market}-{self.contract}', 'code': 404 }))
            await self.close()
        except MaxPoolSizeExceeded as e:
            await self.send(text_data=json.dumps({ 'error': f'Maximum available connections are exceeded.', 'code': 503 }))
            await self.close()

    async def update(self, event):
        """New version of the callback, called via channel layer."""
        if self.range_bids_max and self.range_bids_min:
            event['bids'] = event['bids'][-self.range_bids_max:-self.range_bids_min]
        if self.range_bids_min:
            event['bids'] = event['bids'][:-self.range_bids_min]
        if self.range_bids_max:
            event['bids'] = event['bids'][-self.range_bids_max:]
        if self.range_asks_max and self.range_asks_min:
            event['asks'] = event['asks'][self.range_asks_min:self.range_asks_max]
        if self.range_asks_min:
            event['asks'] = event['asks'][self.range_asks_min:]
        if self.range_asks_max:
            event['asks'] = event['asks'][:self.range_asks_max]
        await self.send(text_data=json.dumps(event, default=str))

    async def receive(self, text_data):
        data = json.loads(text_data)
        if 'depth' in data:
            await self.set_depth(data['depth'])
        if 'range' in data:
            self.range_bids_min = data['range']['bids']['min']
            self.range_bids_max = data['range']['bids']['max']
            self.range_asks_min = data['range']['asks']['min']
            self.range_asks_max = data['range']['asks']['max']
        return

    async def set_depth(self, depth):
        assert self.channel_layer, 'Channel layer is not available'
        assert self.keeper, 'Keeper is not available'
        assert self.group_name, 'Group name is not available'
        old_channel_name = self.group_name
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        self.depth = depth
        self.group_name = f'{self.keeper.key}_{self.depth}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await sync_to_async(self.dispatcher.update_depth)(self.connection_id, old_channel_name, self.group_name)
