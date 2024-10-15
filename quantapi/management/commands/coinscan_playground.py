from ast import Global
import json
from pprint import pprint
from django.core.management.base import BaseCommand
from coingecko import CoinGecko
from markets import kucoin
from markets import binance
from markets.binance import BinanceMarket
from markets.kucoin import KucoinMarket
from markets.mexc import MEXCMarket
from metrichub import calculate_tag_metrics, calculate_tag_weights, cg_match_tags
from quantapi.models import GlobalSymbol, Market, MarketSymbol, Tag


class Command(BaseCommand):
    help = 'Test command'

    def handle(self, *args, **options):
        calculate_tag_weights()



