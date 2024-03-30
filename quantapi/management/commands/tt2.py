from ast import Global
import json
from pprint import pprint
from django.core.management.base import BaseCommand
from markets import kucoin
from markets import binance
from markets.binance import BinanceMarket
from markets.kucoin import KucoinMarket
from markets.mexc import MEXCMarket
from quantapi.models import GlobalSymbol, Market, MarketSymbol


class Command(BaseCommand):
    help = 'Test command'

    def handle(self, *args, **options):
        mxc = Market.objects.filter(exchange_name='MEXC').first().get_interface()
