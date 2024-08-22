import time
from django.core.management.base import BaseCommand, CommandParser, CommandError
from orderpulse.aggregator import AggregatorPool
from quantapi.models import Market, MarketSymbol

class Command(BaseCommand):
    def add_arguments(self, parser: CommandParser) -> None:
        depth_choices = [0.01, 0.1, 1, 10, 100]
        parser.add_argument('symbol', type=str, help='Market symbol (e.g. BTC-USDT)')
        parser.add_argument('markets', type=str, nargs='+', help='Exchange names (e.g. GATEIO,KUCOIN)')
        parser.add_argument('--depth', type=int, help='Depth of the order book', default=1, choices=depth_choices)
        parser.add_argument('--count', type=int, help='Number of bids and asks to display', default=5)
        parser.add_argument('--interval', type=int, help='Interval in seconds to update the order book', default=1)

    def validate(self, options):
        options['markets'] = [m.upper() for m in options['markets']]
        options['symbol'] = options['symbol'].upper().replace('-', '').replace('USDT', '') + '-USDT'
        available_markets = Market.objects.values_list('exchange_name', flat=True)
        for market in options['markets']:
            if not market in available_markets:
                raise CommandError(f'Exchange {market} not registered, choose from: {available_markets}')
            if not MarketSymbol.objects.filter(name=options['symbol'], market__exchange_name=market).exists():
                raise CommandError(f'Market symbol {options["symbol"]} not found in {market}.')

    def print_bids(self, bids, side='bids', length=0):
        print(f'{side.capitalize()} ({length}):')
        for bid in bids:
            print(f'{bid.price:,.2f}\t{bid.size:,.5f}')
        print()

    def print_stats(self, keepers):
        for k in keepers:
            print(f'{k.market}\t{k.state()}')
        print()

    def handle(self, *args, **options):
        self.validate(options)
        agg = AggregatorPool.get(options['symbol'], options['markets'])

        while True:
            try:
                bids, asks = agg.book.get_depth(count=options['count'], depth=options['depth'])
                #bids, asks = k.book.get_best(count=10)  # replace line above with this to see raw price levels
                self.print_bids(bids, 'bids', len(agg.book.bids.keys()))
                print(f'Price: {agg.get_price():,.2f}\n')
                self.print_bids(asks, 'asks', len(agg.book.asks.keys()))
                self.print_stats(agg.keepers.values())
                time.sleep(1)
            except KeyboardInterrupt:
                agg.stop()
                self.stdout.write(self.style.SUCCESS('OK, bye.'))
                break
