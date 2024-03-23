from django.core.management.base import BaseCommand
from quantapi.models import Market
import threading


class Command(BaseCommand):
    help = 'Test command'

    def handle(self, *args, **options):
        market = Market.objects.get(exchange_name='MEXC')
        iface = market.get_interface()

        def on_candle(candle):
            print('new candle:', candle)

        iface.init_websocket('BTC-USDT', '1 min', on_candle)  # init_websocket is sync/blocking
        #threading.Thread(target=iface.init_websocket, args=('BTC-USDT', '1 min', on_candle)).start()  # run in a thread if you want to keep the main thread running
        