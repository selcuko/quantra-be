import json
from django.core.management.base import BaseCommand, CommandError
from quantapi.models import MarketSymbol, GlobalSymbol
from coingecko import CoinGecko

class Command(BaseCommand):
    help = 'Update symbol metrics from a 3rd party provider for all symbols.'

    def handle(self, *args, **options):
        try:
            cg = CoinGecko()
            all_coins = cg.all_coins_with_market_data()
            global_coins = []

            for coin in all_coins:
                gs = GlobalSymbol(
                    cid=coin['id'],
                    name=coin['symbol'].upper().replace('-USD', '') +'-USD',
                    base=coin['symbol'].upper().replace('-USD', ''),
                    image=coin.get('image'),
                    market_cap=coin.get('market_cap'),
                    volume=coin.get('total_volume'),
                    high_24h=coin.get('high_24h'),
                    low_24h=coin.get('low_24h'),
                    price_change_24h=coin.get('price_change_24h'),
                    price_change_percentage_24h=coin.get('price_change_percentage_24h'),
                    circulating_supply=coin.get('circulating_supply'),
                    total_supply=coin.get('total_supply'),
                    max_supply=coin.get('max_supply'),
                    ath=coin.get('ath'),
                    ath_date=coin.get('ath_date'),
                    atl=coin.get('atl'),
                    atl_date=coin.get('atl_date'),
                    data_updated=coin.get('last_updated'),
                    payload=json.dumps(coin),
                    data_source=GlobalSymbol.DataSource.COINGECKO
                )
                gs.calculate()
                if not gs.cid:
                    print(f'Coin {gs.name} not found in CoinGecko API. Skipping...')
                    continue
                global_coins.append(gs)
            
            # check if there are duplicate symbols (cid)
            cid_map = {}
            for s in global_coins:
                if s.cid in cid_map:
                    continue
                cid_map[s.cid] = s

            GlobalSymbol.objects.bulk_create(cid_map.values(), update_conflicts=True, unique_fields=['cid'], update_fields=[
                'market_cap',
                'volume',
                'high_24h',
                'low_24h',
                'price_change_24h',
                'price_change_percentage_24h',
                'circulating_supply',
                'total_supply',
                'max_supply',
                'ath',
                'ath_date',
                'atl',
                'atl_date',
                'data_updated',
                'payload'
            ])
        except KeyboardInterrupt:
            print('Keyboard interrupt detected. Exiting...')
        except Exception as e:
            print(f'An error occurred: {e}')

