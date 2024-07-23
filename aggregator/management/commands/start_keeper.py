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
        bc = k.book.copy()
        ag = Aggregator(symbol.name, k.manager)
        ag.add_keeper(k)

        def callback(diff):
            Book.apply_diff(bc.bids, bc.asks, diff)
            k_best = k.book.get_best(count=3)
            bc_best = bc.get_best(count=3)
            bids = zip(k_best[0], bc_best[0])
            asks = zip(k_best[1], bc_best[1])
            print('Bids:')
            for k_bid, bc_bid in bids:
                style = self.style.SUCCESS if k_bid.price == bc_bid.price and k_bid.size == bc_bid.size else self.style.ERROR
                size_format = f'{k_bid.size:,.5f}' if k_bid.size == bc_bid.size else f'{k_bid.size:,.5f} {bc_bid.size:,.5f}'
                type_diff = '' if type(k_bid) == type(bc_bid) else f'k={type(k_bid)} bc={type(bc_bid)}'
                self.stdout.write(style(f'{k_bid.price:,.2f} {bc_bid.price:,.2f} - {size_format} {type_diff}'))
            print('Asks:')
            for k_ask, bc_ask in asks:
                style = self.style.SUCCESS if k_ask.price == bc_ask.price and k_ask.size == bc_ask.size else self.style.ERROR
                size_format = f'{k_ask.size:,.5f}' if k_ask.size == bc_ask.size else f'{k_ask.size:,.5f} {bc_ask.size:,.5f}'
                type_diff = '' if type(k_ask.price) == type(bc_ask.price) else f'k={type(k_ask.price)} bc={type(bc_ask.price)}'
                self.stdout.write(style(f'{k_ask.price:,.2f} {bc_ask.price:,.2f} - {size_format} {type_diff}'))

        k.add_callback(callback)

        while True:
            try:
                bids, asks = k.book.get_depth(count=5, depth=1)
                queue_c = k.queue.qsize()
                td = f'{k.since_last_update():.2f}s' if k.since_last_update() else 'no updates'
                #bids, asks = k.book.get_best(count=10)
                """print(f'\nBids ({len(k.book.bids.values())}):')
                print_bidlist(bids)
                print(f'\nPrice: {k.book.get_price():,.2f}\tLatency: {td}')  # latency is the timedelta between we receive the update and process it
                print(f'\nAsks ({len(k.book.asks.values())}):')
                print_bidlist(asks)
                print(f'\nQueue: {queue_c} ({k.update_count})')"""
                time.sleep(1)
            except Exception as e:
                traceback.print_exc()
