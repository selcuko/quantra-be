from datetime import datetime
import time
from orderpulse.dispatchers import KeeperDispatchPool
from orderpulse.structures import Delta
from quantapi.models import Market, MarketSymbol
from django.core.management.base import BaseCommand, CommandParser, CommandError


class Command(BaseCommand):

    def add_arguments(self, parser: CommandParser) -> None:
        depth_choices = [0.01, 0.1, 1, 10, 100]
        parser.add_argument('symbol', type=str, help='Market symbol (e.g. BTC-USDT)')
        parser.add_argument('market', type=str, help='Exchange name (e.g. GATEIO)')
        parser.add_argument('--depth', type=int, help='Depth of the order book', default=1, choices=depth_choices)
        parser.add_argument('--count', type=int, help='Number of bids and asks to display', default=5)
        parser.add_argument('--interval', type=int, help='Interval in seconds to update the order book', default=1)

    def print_bids(self, bids, side='bids', length=0):
        print(f'{side.capitalize()} ({length}):')
        for bid in bids:
            print(f'{bid.price:,.2f}\t{bid.size:,.5f}')
        print()

    def validate(self, options):
        options['market'] = options['market'].upper()
        options['symbol'] = options['symbol'].upper().replace('-', '').replace('USDT', '') + '-USDT'
        available_markets = Market.objects.values_list('exchange_name', flat=True)
        if not options['market'] in available_markets:
            raise CommandError(f'Exchange {options["market"]} not registered, choose from: {available_markets}')

    def handle(self, *args, **options):
        self.validate(options)
        try:
            market = Market.objects.get(exchange_name=options['market'])
            symbol = MarketSymbol.objects.get(contract_type=MarketSymbol.ContractType.SPOT, name=options['symbol'], market=market)
        except Market.DoesNotExist:
            raise CommandError(f'Market {options["market"]} not found.')
        except MarketSymbol.DoesNotExist:
            raise CommandError(f'Market symbol {options["symbol"]} not found in {options["market"]}.')

        self.stdout.write(f'Starting dispatcher for {options["symbol"]} on {options["market"]}', ending='\t')
        d = KeeperDispatchPool.get(symbol)
        self.stdout.write(self.style.SUCCESS('OK'))


        def callback(delta:Delta):
            print(f'[{datetime.now()}] received delta seq={delta.sequence}')

        d.add_callback(callback)

        while True:
            try:
                time.sleep(options['interval'])
            except KeyboardInterrupt:
                self.stdout.write(self.style.SUCCESS('OK, bye.'))
                break
