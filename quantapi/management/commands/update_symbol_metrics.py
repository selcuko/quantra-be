import json
from django.core.management.base import BaseCommand
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
        cg = CoinGecko()
        all_coins = cg.all_coins_with_market_data()
        print('OK')
        global_coins = {}
        for coin in all_coins:
            if not coin.get('id'):
                continue
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
                coingecko_response=json.dumps(coin),
                data_source=GlobalSymbol.DataSource.COINGECKO,
                price=float(coin.get('current_price')) if coin.get('current_price') else None,
            )
            gs.calculate()
            if gs.cid not in global_coins or (gs.volume or 0) > (global_coins[gs.cid].volume or 0):
                global_coins[gs.cid] = gs

        GlobalSymbol.objects.bulk_create(global_coins.values(), update_conflicts=True, unique_fields=['cid'], update_fields=[
            'coingecko_response',
            'ath',
            'ath_date',
            'atl',
            'atl_date',
            'volume',
            'market_cap',
            'high_24h',
            'low_24h',
            'circulating_supply',
            'total_supply',
            'max_supply',
            'price',
            'price_change_24h',
            'price_change_percentage_24h',
            'data_updated',
            'supply_ratio',
            'ath_prox',
            'atl_prox',
            'ath_ratio',
            'atl_ratio',
            'volume24h_to_mcap',
        ])

        print('Associating MarketSymbols with GlobalSymbols', end='\t')
        market_symbols = MarketSymbol.objects.prefetch_related('symbol', 'market').all()
        market_update  = []
        global_coins = {gs.cid: gs for gs in GlobalSymbol.objects.all()}

        for ms in market_symbols:
            for gs in global_coins.values():
                if ms.base != gs.base:
                    continue
                if ms.symbol and (ms.symbol.volume or 0) > (gs.volume or 0):
                    continue
                else:
                    ms.symbol = gs
                    market_update.append(ms)
        MarketSymbol.objects.bulk_update(market_update, ['symbol'])
        print('OK')
        sym_to_mar = {}

        print('Updating available markets for GlobalSymbols', end='\t')
        for ms in market_symbols:
            if not ms.symbol:
                continue
            if ms.symbol not in sym_to_mar:
                sym_to_mar[ms.symbol] = []
            sym_to_mar[ms.symbol].append(ms)
        gs_update = []
        for gs, msyms in sym_to_mar.items():
            gs.available_markets = json.dumps([ms.market.exchange_name for ms in msyms if ms.spot_trading_enabled])
            gs_update.append(gs)
        GlobalSymbol.objects.bulk_update(gs_update, ['available_markets'])
        print('OK')
        
        print('Fetching coins from CoinMarketCap', end='\t')
        cmc = CoinMarketCap()
        listings = cmc.listings()
        cmc_symbols = listings['data']
        global_names = {gs.base: gs for gs in GlobalSymbol.objects.all()}
        gs_update = []
        print('OK')
        for cmc_symbol in cmc_symbols:
            gs = global_coins.get(cmc_symbol['slug']) or global_names.get(cmc_symbol['symbol'].upper())
            if not gs:
                continue
            gs.tags_flat = json.dumps(cmc_symbol['tags']) if cmc_symbol.get('tags') else gs.tags_flat
            gs.is_stablecoin = 'stablecoin' in cmc_symbol.get('tags') or gs.base in STABLES
            gs.coinmarketcap_response = json.dumps(cmc_symbol)
            gs_update.append(gs)

        GlobalSymbol.objects.bulk_update(gs_update, ['tags_flat', 'coinmarketcap_response', 'is_stablecoin'])
        print('Done.')

        for gs in GlobalSymbol.objects.all():
            gs.assign_tags()
        
        for tag in Tag.objects.all():
            tag.save()

