import json
from pprint import pprint
from websockets.sync.client import connect

ws = connect('wss://api.example.com/ws/candles/BYBIT/BTC-USDT/')
while True:
    payload = json.loads(ws.recv())
    pprint(payload)
    if payload.get('error'):
        break
