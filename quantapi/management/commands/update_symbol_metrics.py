from ast import Global
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
                try:
                    gs, created = GlobalSymbol.objects.get_or_create(
                    data_source=GlobalSymbol.DataSource.COINGECKO,
                    cid=coin['id'],
                    name=coin['symbol'].upper()+'-USD',
                    defaults={
                        'base': coin['symbol'].upper(),
                        'display': coin['name'],
                        'image': coin['image'],
                        'market_cap': coin['market_cap'],
                        'volume': coin['total_volume'],
                        'high_24h': coin['high_24h'],
                        'low_24h': coin['low_24h'],
                        'price_change_24h': coin['price_change_24h'],
                        'price_change_percentage_24h': coin['price_change_percentage_24h'],
                        'circulating_supply': coin['circulating_supply'],
                        'total_supply': coin['total_supply'],
                        'max_supply': coin['max_supply'],
                        'ath': coin['ath'],
                        'ath_date': coin['ath_date'],
                        'atl': coin['atl'],
                        'atl_date': coin['atl_date'],
                        'data_updated': coin['last_updated'],
                        'payload': coin
                    }
                )
                    if not created:
                        print(f'{gs.name} already exists')
                except Exception as e:
                    print(f'Failed to create {coin["symbol"]}')
                print(f'Created {gs.name}')
        except KeyboardInterrupt:
            print('Keyboard interrupt detected. Exiting...')
        except Exception as e:
            print(f'An error occurred: {e}')

