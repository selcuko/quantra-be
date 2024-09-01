import json
from pprint import pprint
from websockets.sync.client import connect

ws = connect('ws://localhost:8000/ws/miniorderbook/BINANCE/BTC-USDT/?contract=FUTURES')
while True:
    try:
        try:
            payload = json.loads(ws.recv(timeout=.5))
        except TimeoutError as e:
            continue
        except KeyboardInterrupt as e:
            break
        pprint(payload)
        if payload.get('error'):
            break
    except Exception as e:
        break
print('closing connection')
ws.close()
print('closed')
