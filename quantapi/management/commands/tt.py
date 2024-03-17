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
        markets = Market.objects.filter(mainnet_enabled=True)
        interfaces = {
            'KUCOIN': markets.filter(exchange_name='KUCOIN').first().get_interface(),
            'BINANCE': markets.filter(exchange_name='BINANCE').first().get_interface(),
            'MEXC': markets.filter(exchange_name='MEXC').first().get_interface(),
        }
        symbols_to_update = []
        for gs in GlobalSymbol.objects.exclude(available_markets='[]'):
            symbols = gs.symbols.filter(market__mainnet_enabled=True, spot_trading_enabled=True)
            for symbol in symbols:
                interface = interfaces[symbol.market.exchange_name]
                try:
                    h4_candle = interface.get_last_klines(symbol.name, '4 hour', 2, retry=0)[0]
                    h4_candle = interface.format_candle(h4_candle)
                    symbol.hour4_volume = h4_candle['volume'] * h4_candle['price']
                    symbol.hour4_volume_date = h4_candle['time']

                    d1_candles = interface.get_last_klines(symbol.name, '1 day', 61, retry=0)[0:-1]
                    d1_candles = [interface.format_candle(c) for c in d1_candles]
                    if len(d1_candles) >= 10:
                        symbol.day10_volume = sum([c['volume'] * c['price'] for c in d1_candles[-10:]])
                        symbol.day10_volume_date = d1_candles[-10]['time']
                    if len(d1_candles) >= 30:
                        symbol.day30_volume = sum([c['volume'] * c['price'] for c in d1_candles[-30:]])
                        symbol.day30_volume_date = d1_candles[-30]['time']
                    if len(d1_candles) >= 60:
                        symbol.day60_volume = sum([c['volume'] * c['price'] for c in d1_candles[-60:]])
                        symbol.day60_volume_date = d1_candles[-60]['time']
                    symbols_to_update.append(symbol)
                    print('.', end='', flush=True)
                except Exception as e:
                    print('x', end='', flush=True)
        MarketSymbol.objects.bulk_update(symbols_to_update, ['hour4_volume', 'hour4_volume_date', 'day10_volume', 'day10_volume_date', 'day30_volume', 'day30_volume_date', 'day60_volume', 'day60_volume_date'])





