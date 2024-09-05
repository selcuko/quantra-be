import asyncio
import json
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from quantapi.models import MarketSymbol
from orderpulse.pools import TickerPool


class TickerConsumer(AsyncWebsocketConsumer):
    def get_symbol(self):
        try:
            symbol = self.scope['url_route']['kwargs']['symbol'].upper()
            market = self.scope['url_route']['kwargs']['market'].upper()
            contract = self.scope['url_route']['kwargs'].get('contract', 'SPOT').upper()
            self.symbol = MarketSymbol.objects.get(contract_type=contract, name=symbol, market__exchange_name=market)
            self.interface = self.symbol.market.get_interface()
            return self.symbol
        except MarketSymbol.DoesNotExist:
            raise Exception(f'Symbol {symbol} not found in {market}-{contract}.')
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
        await sync_to_async(TickerPool.get)(self.symbol, self.callback)

    async def disconnect(self, close_code):
        self.connected = False
        await sync_to_async(TickerPool.remove_callback)(self.symbol, self.callback)

    async def receive(self, text_data):
        pass

    def callback(self, candle: dict):
        if not self.connected:
            return
        asyncio.run(self.send(text_data=json.dumps(candle, default=str)))