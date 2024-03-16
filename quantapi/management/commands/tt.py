import json
from pprint import pprint
from django.core.management.base import BaseCommand
from markets.kucoin import KucoinMarket
from quantapi.models import GlobalSymbol, Market


class Command(BaseCommand):
    help = 'Test command'

    def handle(self, *args, **options):
        kc = Market.objects.filter(exchange_name='KUCOIN').first().get_interface()
        snapshot = kc.orderbook_snapshot('XRP-USDT')
        with open('orderbook.json', 'w') as f:
            json.dump(snapshot, f, indent=4)
        pprint(snapshot)
