from django.core.management.base import BaseCommand, CommandError

from models import OHLCVDataset
from quantapi.models import MarketSymbol

class Command(BaseCommand):
    help = 'Run LiveLoop for a given session.'

    def add_arguments(self, parser):
        parser.add_argument('symbol', type=str)
        parser.add_argument('market', type=str)
        parser.add_argument('--interval', type=str, default='1 min')
        parser.add_argument('--contract_type', type=str, default='SPOT')






    def handle(self, *args, **options):
        symbol = options['symbol']
        market = options['market']
        interval = options['interval']
        contract_type = options['contract_type']
        
        symbol_object = MarketSymbol.objects.get(base=symbol.upper(), market__exchange_name=market.upper(), contract_type=contract_type.upper())
        market_object = symbol_object.market
        interface = market_object.get_interface()
        klines = interface.get_last_klines(symbol_object, interval)
        klines_df = OHLCVDataset(klines)

        print(klines_df.head())

        
       
