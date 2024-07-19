import json
from pprint import pprint
from websockets.sync.client import connect

ws = connect('ws://localhost:8000/ws/orderbook/')
ws.send(json.dumps({
    'type': 'subscribe',
    'market': 'BYBIT',
    'symbol': 'BTC-USDT',
    'depth': 1,
    'count': 5
}))
while True:
    payload = json.loads(ws.recv())
    pprint(payload)
    if payload.get('error'):
        break
