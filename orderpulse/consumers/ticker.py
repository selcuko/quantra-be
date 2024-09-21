import json
import re
from urllib.parse import parse_qs
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from orderpulse.dispatchers import TickerDispatch
from quantapi.models import Market, MarketSymbol


def add_space_after_number(string: str) -> str:
    return re.sub(r'(\d+)', r'\1 ', string)


class TickerConsumer(AsyncWebsocketConsumer):
    dispatcher = TickerDispatch()

    async def connect(self):
        self.group_name: str|None = None
        self.connected = False
        self.symbol: MarketSymbol|None = None

        query_params = parse_qs(self.scope['query_string'].decode('utf-8'))
        self.contract = query_params.get('contract', ['SPOT'])[0]
        self.interval = add_space_after_number(query_params.get('interval', ['1min'])[0])
        self.market = self.scope['url_route']['kwargs']['market']
        self.symbol_name = self.scope['url_route']['kwargs']['symbol']
        print(self.market, self.symbol_name, self.contract, self.interval)

        self.connection_id = str(self.channel_name)

        await self.accept()
        await self.subscribe()
        self.connected = True

    async def disconnect(self, close_code):
        await sync_to_async(self.dispatcher.drop, thread_sensitive=False)(self.connection_id, self.symbol, self.interval)
        if self.group_name and self.channel_layer:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    def get_symbol(self, market, symbol) -> MarketSymbol:
        assert self.connection_id, 'Connection ID is not available'
        market = Market.objects.get(exchange_name=market)
        symbol = MarketSymbol.objects.get(contract_type=self.contract, name=symbol, market=market)
        return symbol

    async def get_symbol_key(self) -> str:
        assert self.symbol, 'Symbol is not available'
        key = await sync_to_async(self.symbol.key)()
        return key

    async def subscribe(self):
        assert self.channel_layer, 'Channel layer is not available'
        assert self.connection_id, 'Connection ID is not available'
        if self.connected:
            await self.send(text_data='Already connected')
            return
        try:
            self.symbol = await sync_to_async(self.get_symbol)(self.market, self.symbol_name)
            key = f'{await self.get_symbol_key()}.{self.interval}'
            self.group_name = key.replace(' ', '')
            await sync_to_async(self.dispatcher.get)(self.connection_id, self.symbol, self.interval)
            await self.channel_layer.group_add(self.group_name, self.channel_name)
        except Market.DoesNotExist:
            await self.send(text_data=json.dumps({ 'error': f'Market {self.market} not found', 'code': 404 }))
            await self.close()
        except MarketSymbol.DoesNotExist:
            await self.send(text_data=json.dumps({ 'error': f'Symbol {self.symbol_name} not found in {self.market}-{self.contract}', 'code': 404 }))
            await self.close()

    async def update(self, event):
        assert self.connected, 'Connection is not established'
        await self.send(text_data=json.dumps(event, default=str))
