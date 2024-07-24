import time
from quantapi.models import Market, MarketSymbol
from django.core.management.base import BaseCommand, CommandParser, CommandError
from orderpulse.keeper import KeeperPool


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
            symbol = MarketSymbol.objects.get(name=options['symbol'], market=market)
        except Market.DoesNotExist:
            raise CommandError(f'Market {options["market"]} not found.')
        except MarketSymbol.DoesNotExist:
            raise CommandError(f'Market symbol {options["symbol"]} not found in {options["market"]}.')

        self.stdout.write(f'Starting keeper for {options["symbol"]} on {options["market"]}')
        k = KeeperPool.get(symbol)
        k.start()

        while True:
            try:
                bids, asks = k.book.get_depth(count=options['count'], depth=options['depth'])
                #bids, asks = k.book.get_best(count=10)  # replace line aboce with this to see raw price levels
                self.print_bids(bids, 'bids', len(k.book.bids.keys()))
                print(f'\nPrice: {k.book.get_price():,.2f}\n')
                self.print_bids(asks, 'asks', len(k.book.asks.keys()))
                print(f'\nStatus: {k.state()}')
                print()
                time.sleep(options['interval'])
            except KeyboardInterrupt:
                k.stop()
                self.stdout.write(self.style.SUCCESS('OK, bye.'))
                break
