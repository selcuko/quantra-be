from datetime import datetime
import sys
import time

from orderpulse.aggregator import Aggregator
from orderpulse.manager import BookManager
from orderpulse.structures import Book, Delta
from quantapi.models import MarketSymbol
from django.core.management.base import BaseCommand
from orderpulse.keeper import Keeper


def print_bids(bids, side='bids', length=3):
    print(f'{side.capitalize()} ({length}):')
    for bid in bids:
        print(f'{bid.price:,.2f}\t{bid.size:,.5f}')
    print()


class Command(BaseCommand):
    def handle(self, *args, **options):
        symbol = MarketSymbol.objects.get(market__exchange_name='GATEIO', name='BTC-USDT')
        s2 = MarketSymbol.objects.get(market__exchange_name='BYBIT', name='BTC-USDT')
        manager = BookManager()
        manager.start()
        keeper = Keeper(symbol, manager)
        keeper2 = Keeper(s2, manager)
        keeper.start()
        keeper2.start()

        aggregator = Aggregator(manager)
        aggregator.add_keeper(keeper)
        aggregator.add_keeper(keeper2)

        started = datetime.now()

        while True:
            try:
                k_bids, k_asks = keeper.book.get_best(3)
                a_bids, a_asks = aggregator.book.get_best(3)
                #print_bids(k_bids, 'bids', len(keeper.book.bids.values()))
                #print_bids(k_asks, 'asks', len(keeper.book.asks.values()))
                print_bids(a_bids, 'bids', len(aggregator.book.bids.values()))
                print_bids(a_asks, 'asks', len(aggregator.book.asks.values()))
                time.sleep(1)
                if 0 and (datetime.now() - started).seconds > 25:
                    print(aggregator.book)
                    print(keeper.book)
                    sys.exit()
            except KeyboardInterrupt:
                keeper.stop()
                self.stdout.write(self.style.SUCCESS('OK, bye.'))
                break
