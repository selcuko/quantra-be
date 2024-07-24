from datetime import datetime
import time
import traceback
from orderpulse.aggregator import Aggregator
from orderpulse.structures import Book
from quantapi.models import Market, MarketSymbol
from django.core.management.base import BaseCommand
from orderpulse.keeper import KeeperPool

def print_bidlist(bids):
    for bid in bids:
        delta = datetime.now() - bid.updated
        print(f'{bid.price:,.2f}\t{bid.size:8,.5f}\t[{delta.seconds}s]')

class Command(BaseCommand):
    def handle(self, *args, **options):
        market = Market.objects.get(exchange_name='GATEIO')
        market.get_interface()
        symbol = MarketSymbol.objects.get(name='BTC-USDT', market=market)
        k = KeeperPool.get(symbol)
        k.start()
        time.sleep(2)
        bc = Book(k.manager)
        bc.apply_diff(bc.bids, bc.asks, { 'bids': (k.book.bids), 'asks': (k.book.asks) })

        k.add_callback(lambda diff: Book.apply_diff(bc.bids, bc.asks, diff))

        ag = Aggregator(symbol.name, k.manager)
        ag.add_keeper(k)

        while True:
            try:
                k_bids, k_asks = k.book.get_best(count=3)
                bc_bids, bc_asks = bc.get_best(count=3)
                ag_bids, ag_asks = ag.book.get_best(count=3)
                bids = zip(k_bids, bc_bids, ag_bids)
                asks = zip(k_asks, bc_asks, ag_asks)
                print('Bids:')
                for k_bid, bc_bid, ag_bid in bids:
                    style1 = self.style.SUCCESS if k_bid.price == bc_bid.price and k_bid.size == bc_bid.size else self.style.ERROR
                    style2 = self.style.SUCCESS if k_bid.price == ag_bid.price and k_bid.size == ag_bid.size else self.style.ERROR
                    size_format = f'{k_bid.size:,.5f}' if k_bid.size == bc_bid.size == ag_bid.size else f'{k_bid.size:,.5f} {bc_bid.size:,.5f} {ag_bid.size:,.5f}'
                    type_diff = '' if type(k_bid) == type(bc_bid) == type(ag_bid) else f'k={type(k_bid)} bc={type(bc_bid)} ag={type(ag_bid)}'
                    self.stdout.write(style1(f'{k_bid.price:,.2f} {bc_bid.price:,.2f}'), ending=' ')
                    self.stdout.write(style2(f'{ag_bid.price:,.2f}'), ending=' ')
                    self.stdout.write(f'- {size_format} {type_diff}')
                print('Asks:')
                for k_ask, bc_ask, ag_ask in asks:
                    style1 = self.style.SUCCESS if k_ask.price == bc_ask.price and k_ask.size == bc_ask.size else self.style.ERROR
                    style2 = self.style.SUCCESS if k_ask.price == ag_ask.price and k_ask.size == ag_ask.size else self.style.ERROR
                    size_format = f'{k_ask.size:,.5f}' if k_ask.size == bc_ask.size == ag_ask.size else f'{k_ask.size:,.5f} {bc_ask.size:,.5f} {ag_ask.size:,.5f}'
                    type_diff = '' if type(k_ask) == type(bc_ask) == type(ag_ask) else f'k={type(k_ask)} bc={type(bc_ask)} ag={type(ag_ask)}'
                    self.stdout.write(style1(f'{k_ask.price:,.2f} {bc_ask.price:,.2f}'), ending=' ')
                    self.stdout.write(style2(f'{ag_ask.price:,.2f}'), ending=' ')
                    self.stdout.write(f'- {size_format} {type_diff}')
                time.sleep(1)
            except KeyboardInterrupt:
                print('\nOK, bye.')
                k.stop()
                break