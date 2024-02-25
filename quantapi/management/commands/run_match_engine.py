from datetime import datetime
import json
from django.core.management.base import BaseCommand
from quantapi.models import Market
from websockets.sync.client import connect
from match import MatchEngine


class Command(BaseCommand):
    help = 'Test command'

    def handle(self, *args, **options):
        iface = Market.objects.get(exchange_name='MEXC').get_interface()
        iface.init_match_engine('BTC-USDT', '1 min', print)
