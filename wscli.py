import json
from websockets.sync.client import connect

ws = connect('ws://localhost:8000/ws/orderbook/')
ws.send(json.dumps({
    'type': 'subscribe',
}))
while True:
    payload = ws.recv()
    print('Received:', payload)
