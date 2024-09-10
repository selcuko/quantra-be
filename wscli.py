import json
from pprint import pprint
from websockets.sync.client import connect

ws = connect('ws://localhost:8000/ws/miniorderbook/BINANCE/BTC-USDT/?contract=SPOT')
setdepth = True
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
        if not setdepth:
            ws.send(json.dumps({'depth': 100}))
            setdepth = True
    except Exception as e:
        break
print('closing connection')
ws.close()
print('closed')
