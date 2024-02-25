from datetime import datetime
import json
from django.core.management.base import BaseCommand
from quantapi.models import Market
from websockets.sync.client import connect
from match import MatchEngine


class Command(BaseCommand):
    help = 'Test command'

    def handle(self, *args, **options):
        iface = Market.objects.get(exchange_name='KUCOIN').get_interface()
        token = iface.get_websocket_token()
        uri = f'wss://ws-api-spot.kucoin.com/?token={token}&[connectId=1234]'
        ws = connect(uri)
        welcome = ws.recv()
        sub = {
            "id": 1545910660741,
            "type": "subscribe",
            "topic": "/market/match:BTC-USDT",
            "privateChannel": False,
            "response": True
        }
        ws.send(json.dumps(sub))
        ack = ws.recv()
        me = MatchEngine('1 min', print)
        last_ping = datetime.now()
        while True:
            if (datetime.now() - last_ping).seconds > 30:
                ws.send(json.dumps({"id": 1545910660741, "type": "ping"}))
                last_ping = datetime.now()
            data = json.loads(ws.recv())
            if data.get('type') == 'pong':
                continue
            if not data.get('subject') == 'trade.l3match':
                print('Not a trade.l3match message', data)
                continue
            me.on_match(data.get('data'))
