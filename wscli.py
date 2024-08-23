import json
from pprint import pprint
from websockets.sync.client import connect

ws = connect('ws://localhost:8000/ws/candles/BYBIT/BTC-USDT/')
while True:
    payload = json.loads(ws.recv())
    pprint(payload)
    if payload.get('error'):
        break
