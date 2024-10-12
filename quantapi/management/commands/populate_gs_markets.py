import json
import os
import time
from django.core.management.base import BaseCommand, CommandError
from quantapi.models import GlobalSymbol, MarketSymbol
from coingecko import CoinGecko


class Command(BaseCommand):
    def handle(self, *args, **options):
        symbols = GlobalSymbol.objects.filter(symbols__isnull=False).prefetch_related('symbols__market').distinct()
        update = []
        for s in symbols:
            s.markets = list(set([ms.market.exchange_name for ms in s.symbols.all()]))
            update.append(s)
            print('Updated', s.base)
        GlobalSymbol.objects.bulk_update(update, ['markets'])
        
