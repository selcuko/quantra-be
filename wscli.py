from websockets.sync.client import connect

ws = connect('ws://localhost:8000/ws/some_path/')
ws.send('{"message": "Hello"}')
recv = ws.recv()
print(recv)