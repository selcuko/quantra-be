import json
from websockets.sync.client import connect
import time


ws = connect("ws://localhost:8765")
ws.send(json.dumps({
    'channel': 'subscribe',
    'symbol': 277997
}))
ack = ws.recv()
print('ACK', ack)
ws.send(json.dumps({
    'channel': 'subscribe',
    'symbol': 246670
}))
ack = ws.recv()
print('ACK', ack)
ws.send(json.dumps({
    'channel': 'subscribe',
    'symbol': 251369
}))
ack = ws.recv()
print('ACK', ack)

while True:
    msg = ws.recv()
    print(msg)