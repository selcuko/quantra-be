import asyncio
from datetime import datetime, timedelta
import json
import threading
import time
from websockets.server import serve, WebSocketServerProtocol
from logger import logger
from models import OrderBook
from orderbook import BookKeeper, BookMaster
from asgiref.sync import sync_to_async


# write ma a websocker server that takes subscriptions based on MarketSymbol
# and has a callback function that each time gets called, sends the subscribed
# clients the argument it took (a dictionary)

def start_orderbook_server():
    subs: dict[WebSocketServerProtocol, BookMaster] = {}
    pings: dict[WebSocketServerProtocol, datetime] = {}
    print('Starting orderbook server...')

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
        from quantapi.models import MarketSymbol

        async for message in websocket:
            message = json.loads(message)
            channel = message.get('channel')
            if channel == 'subscribe':
                symbol_name = message.get('symbol')
                market_name = message.get('market').split(',')
                symbols = []
                symbols = await sync_to_async(MarketSymbol.objects.filter)(name=symbol_name, market__exchange_name__in=market_name)
                symbols = await sync_to_async(symbols.prefetch_related)('market')
                symbols = await sync_to_async(list)(symbols)
                if len(symbols) != len(market_name):
                    not_found = [m for m in market_name if m not in [s.market.exchange_name for s in symbols]]
                    for nf in not_found:
                        await websocket.send(json.dumps({
                            'channel': 'subscribe',
                            'symbol': symbol_name,
                            'market': nf,
                            'result': 404,
                            'message': f'No such symbol {symbol_name} in {nf}.'
                        }))
                if len(symbols) == 0:
                    continue
                keepers = []
                for symbol in symbols:
                    keeper = await sync_to_async(BookKeeper)(symbol)
                    keeper.start()
                    keepers.append(keeper)
                    await websocket.send(json.dumps({
                        'channel': 'subscribe',
                        'symbol': symbol_name,
                        'market': symbol.market.exchange_name,
                        'result': 200,
                        'message': f'Subscribed to {symbol_name}.'
                    }))
                master = subs.get(websocket)
                if not master:
                    master = await sync_to_async(BookMaster)(symbols[0])
                    master.add_callback(keeper_callback)
                    subs[websocket] = master
                    pings[websocket] = datetime.now()
                for keeper in keepers:
                    master.add_keeper(keeper)
                await websocket.send(json.dumps({
                    'channel': 'subscribed',
                    'symbol': symbol_name,
                    'result': 200,
                    'message': f'Subscribed to orderbooks of {symbols}.'
                }))
                print(f'Subscribed to {symbols[0].name}@{market_name} orderbook.')

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
        payload = {
            'channel': 'update',
            'update': update,
            'snapshot': snapshot
        }
        asyncio.run_coroutine_threadsafe(
            websocket.send(json.dumps(payload)), loop)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    #kill_afk_task = asyncio.get_event_loop().create_task(kill_afk())
    #server_task = asyncio.get_event_loop().create_task(start_server())
    #group = asyncio.gather(server_task)
    start_server = serve(server, 'localhost', 8765)
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()

if __name__ == '__main__':

    # Create a new thread to run the websocket server
    websocket_thread = threading.Thread(target=start_orderbook_server)
    websocket_thread.start()

    # Ensure the main thread doesn't exit (e.g., if this code is in a script)
    websocket_thread.join()
