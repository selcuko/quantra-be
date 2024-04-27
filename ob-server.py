import asyncio
from datetime import datetime, timedelta
import json
import threading
import time
import traceback
from websockets.server import serve, WebSocketServerProtocol
from logger import logger
from models import OrderBook
from orderbook import BookKeeper, BookMaster
from quantapi.models import MarketSymbol
from asgiref.sync import sync_to_async


# write ma a websocker server that takes subscriptions based on MarketSymbol
# and has a callback function that each time gets called, sends the subscribed
# clients the argument it took (a dictionary)

def start_server():
    subs: dict[WebSocketServerProtocol, BookMaster] = {}
    pings: dict[WebSocketServerProtocol, datetime] = {}

    def get_ws(master):
        for ws, m in subs.items():
            if m == master:
                return ws
        return None

    async def kill_afk():
        while True:
            for ws, ping in pings.items():
                if td := (datetime.now() - ping > timedelta(seconds=30)):
                    print('Killing a socket, its old this much:', td)
                    master = subs[ws]
                    master.stop()
                    del subs[ws]
                    del pings[ws]
                    await ws.close(reason='AFK')
            time.sleep(1)

    async def server(websocket: WebSocketServerProtocol, path):
        async for message in websocket:
            message = json.loads(message)
            channel = message.get('channel')
            if channel == 'subscribe':
                symbol_name = message.get('symbol')
                market_name = message.get('market')
                symbol = None
                try:
                    symbol = (await sync_to_async(MarketSymbol.objects.get)(name=symbol_name, market__exchange_name=market_name))
                except MarketSymbol.DoesNotExist:
                    logger.error(
                        f'No such symbol {symbol_name} on {market_name}.')
                    await websocket.send(json.dumps({
                        'channel': 'subscribe',
                        'symbol': symbol_name,
                        'result': 404,
                        'message': f'No such symbol {symbol_name} on {market_name}.'
                    }))
                    continue

                keeper = await sync_to_async(BookKeeper)(symbol)
                keeper.start()
                master = subs.get(websocket)
                if not master:
                    master = await sync_to_async(BookMaster)(symbol)
                    master.add_callback(keeper_callback)
                    subs[websocket] = master
                    pings[websocket] = datetime.now()
                master.add_keeper(keeper)
                await websocket.send(json.dumps({
                    'channel': 'subscribe',
                    'symbol': symbol_name,
                    'result': 200,
                    'message': f'Subscribed to {symbol.name} orderbook.'
                }))
                print(f'Subscribed to {symbol.name}@{market_name} orderbook.')

            elif channel == 'unsubscribe':
                symbol = message.get('symbol')
            elif channel == 'keepalive':
                pings[websocket] = datetime.now()
            else:
                print('Unknown channel')

    def keeper_callback(master: BookMaster, data: OrderBook):
        websocket = get_ws(master)
        if not websocket:
            logger.warning(f'No websocket for {master}')
            return
        update = data.json()
        snapshot = master.orderbook.json()
        asyncio.run_coroutine_threadsafe(
            websocket.send(json.dumps(snapshot)), loop)

    asyncio.set_event_loop(loop)
    #kill_afk_task = asyncio.get_event_loop().create_task(kill_afk())
    #server_task = asyncio.get_event_loop().create_task(start_server())
    #group = asyncio.gather(server_task)
    start_server = serve(server, 'localhost', 8765)
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()


loop = asyncio.new_event_loop()

# Create a new thread to run the websocket server
websocket_thread = threading.Thread(target=start_server)
websocket_thread.start()

# Ensure the main thread doesn't exit (e.g., if this code is in a script)
websocket_thread.join()
