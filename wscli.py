import json
from pprint import pprint
from websockets.sync.client import connect

ws = connect('ws://localhost:8000/ws/miniagg/BTC-USDT/BINANCE,KUCOIN,MEXC,GATEIO/')
while True:
    payload = json.loads(ws.recv())
    pprint(payload)
    if payload.get('error'):
        break
