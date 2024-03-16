import json
from django.core.management.base import BaseCommand, CommandError
from coinmcap import CoinMarketCap
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
                'payload',
                'volume24h_to_mcap',
                'atl_ratio',
                'ath_ratio',
            ])
        except KeyboardInterrupt:
            print('Keyboard interrupt detected. Exiting...')
        except Exception as e:
            print(f'An error occurred: {e}')

        # associate MarketSymbol with GlobalSymbol
        market_symbols = MarketSymbol.objects.prefetch_related('symbol', 'market').all()
        global_symbols = GlobalSymbol.objects.all()
        unique_symbols = {}
        market_update  = []
        for gs in global_symbols:
            if gs.name not in unique_symbols:
                unique_symbols[gs.name] = gs
            new_vol = gs.volume or 0
            old_vol = unique_symbols[gs.name].volume or 0
            if new_vol > old_vol:
                unique_symbols[gs.name] = gs
        for ms in market_symbols:
            for us in unique_symbols.values():
                if ms.base == us.base:
                    ms.symbol = us
                    market_update.append(ms)
                    break
        MarketSymbol.objects.bulk_update(market_update, ['symbol'])
        market_symbols = MarketSymbol.objects.prefetch_related('symbol', 'market').all()
        gs_update = []
        for i, gs in enumerate(GlobalSymbol.objects.all()):
            ms = [ms for ms in market_symbols if ms.symbol == gs]
            gs.set_markets(save=False, ms=ms)
            gs_update.append(gs)
        GlobalSymbol.objects.bulk_update(gs_update, ['available_markets'])

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
            gs.tags = json.dumps(symbol['tags']) if symbol.get('tags') else gs.tags
            gs.coinmarketcap_response = json.dumps(symbol)
            gs_update.append(gs)
        GlobalSymbol.objects.bulk_update(gs_update, ['tags', 'coinmarketcap_response'])

