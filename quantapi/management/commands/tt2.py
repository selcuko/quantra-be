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
from quantapi.models import GlobalSymbol, Market, MarketSymbol, Tag


class Command(BaseCommand):
    help = 'Test command'

    def print_category_info(self):
        symbols = GlobalSymbol.objects.all()
        categories = {}

        for symbol in symbols:
            tags = json.loads(symbol.tags_flat or '[]')
            for tag in tags:
                if tag not in categories:
                    categories[tag] = []
                categories[tag].append(symbol)

        for category, symbols in categories.items():
            print(f'{category}: {len(symbols)}')

    def handle(self, *args, **options):
        symbols = GlobalSymbol.objects.all()
        for symbol in symbols:
            tags = json.loads(symbol.tags_flat or '[]')
            for tag_name in tags:
                tag = Tag.objects.get_or_create(name=tag_name)[0]
                symbol.tags.add(tag)
                print('.', end='', flush=True)


