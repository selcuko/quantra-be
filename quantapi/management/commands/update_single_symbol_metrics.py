import json
from pprint import pprint
from django.core.management.base import BaseCommand
from django.utils import timezone
from coinmcap import CoinMarketCap
from quantapi.models import MarketSymbol, GlobalSymbol, Tag
from coingecko import CoinGecko

STABLES = ['USDT', 'BUSD', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'USDD', 'USDe',
           'FRAX', 'USTC', 'PYUSD', 'USDP', 'USDJ', 'GUSD', 'EURS', 'LUSD',
           'vUSDC', 'USDX', 'BUSD', 'MKUSD', 'SBD', 'AEUR', 'vBUSD', 'EURC',
           'SUSD', 'RSV', 'CUSD', 'EURt', 'XSGD', 'vUSDT', 'USDK', 'ZUSD',
           'USDV']

class Command(BaseCommand):
    help = 'Update symbol metrics from a 3rd party provider for all symbols.'

    def handle(self, *args, **options):
        print('Fetching coins from CoinGecko', end='\t')
        my_single_coin = 'ripple'
        cg = CoinGecko()
        coin = cg.coin_by_cid(my_single_coin)
        print('OK')
        global_coins = {}

        # Try to fetch the existing instance from the database
        gs = GlobalSymbol.objects.get(cid=coin['id'])
        # Update only the specified fields
        for field, value in cg.full_payload_to_dict(coin).items():
            setattr(gs, field, value)
        gs.calculate()
        gs.save()
            
        print(f"Updated existing GlobalSymbol: {gs.cid}")


                
