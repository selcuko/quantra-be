import json
from django.core.management.base import BaseCommand
from coinmcap import CoinMarketCap
from quantapi.models import GlobalSymbol, Market


class Command(BaseCommand):
    help = 'Test command'

    def handle(self, *args, **options):
        cmc = CoinMarketCap()
        listings = cmc.listings()
        cmc_symbols = listings['data']
        global_symbols = list(GlobalSymbol.objects.all())
        gs_names = [gs.base for gs in global_symbols]
        gs_update = []

        for symbol in cmc_symbols:
            
            if symbol['symbol'] not in gs_names:
                print('x', end='')
                continue
            print('.', end='')
            gs = [gs for gs in global_symbols if gs.base == symbol['symbol']][0]
            gs.tags = json.dumps(symbol['tags'])
            gs.coinmarketcap_response = json.dumps(symbol)
            gs_update.append(gs)
        GlobalSymbol.objects.bulk_update(gs_update, ['tags', 'coinmarketcap_response'])
