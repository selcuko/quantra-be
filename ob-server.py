import asyncio
import json
import threading
import traceback
from websockets.server import serve, WebSocketServerProtocol
from logger import logger
from orderbook import BookKeeper, BookMaster
from quantapi.models import MarketSymbol
from asgiref.sync import sync_to_async


# write ma a websocker server that takes subscriptions based on MarketSymbol
# and has a callback function that each time gets called, sends the subscribed
# clients the argument it took (a dictionary)

def start_server():
    subs:dict[WebSocketServerProtocol, BookMaster] = {}

    def get_ws(master):
        for ws, m in subs.items():
            if m == master:
                return ws
        return None

    async def server(websocket:WebSocketServerProtocol, path):
        async for message in websocket:
            message = json.loads(message)
            channel = message.get('channel')
            if channel == 'subscribe':
                symbol_name = message.get('symbol')
                market_name = message.get('market')
                symbol = None
                try:
                    symbol = (await sync_to_async(MarketSymbol.objects.get)(name=symbol_name, market__exchange_name=market_name))
                    if not symbol:
                        raise ValueError(f'No symbol found for {symbol_name}@{market_name}')
                except:
                    print('Error:', symbol_name, market_name, traceback.format_exc())
                    continue

                keeper = await sync_to_async(BookKeeper)(symbol)
                keeper.start()
                master = subs.get(websocket)
                if not master:
                    master = await sync_to_async(BookMaster)(symbol)
                    master.add_callback(keeper_callback)
                    subs[websocket] = master
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

            else:
                print('Unknown channel')

    def keeper_callback(master, data):
        websocket = get_ws(master)
        if not websocket:
            logger.warning(f'No websocket for {master}')
            return
        asyncio.run_coroutine_threadsafe(websocket.send(json.dumps(data)), loop)



    asyncio.set_event_loop(loop)
    start_server = serve(server, "localhost", 8765)
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()

loop = asyncio.new_event_loop()

# Create a new thread to run the websocket server
websocket_thread = threading.Thread(target=start_server)
websocket_thread.start()

# Ensure the main thread doesn't exit (e.g., if this code is in a script)
websocket_thread.join()