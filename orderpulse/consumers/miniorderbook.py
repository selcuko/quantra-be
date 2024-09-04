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
    DEFAULT_DEPTH = 1
    DEFAULT_COUNT = 10
    dispatcher = KeeperDispatch()

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
            await self.channel_layer.group_add(self.keeper.key, self.channel_name)
        except Market.DoesNotExist:
            await self.send(text_data=json.dumps({ 'error': f'Market {market} not found', 'code': 404 }))
            return
        except MarketSymbol.DoesNotExist:
            await self.send(text_data=json.dumps({ 'error': f'Symbol {symbol} not found in {market}-{self.contract}', 'code': 404 }))
            return
        except MaxPoolSizeExceeded as e:
            await self.send(text_data=json.dumps({ 'error': f'Maximum available connections are exceeded.', 'code': 503 }))
            return

    async def update(self, event):
        """New version of the callback, called via channel layer."""
        await self.send(text_data=json.dumps(event, default=str))
