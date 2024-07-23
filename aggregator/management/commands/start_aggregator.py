from datetime import datetime
import time
from django.core.management.base import BaseCommand
from numpy import size
from orderpulse.consolidator import AggregatorPool


class Command(BaseCommand):
    def handle(self, *args, **options):
        markets = ['GATEIO']
        agg = AggregatorPool.get('BTC-USDT', markets)
        time.sleep(5)
        kep = agg.keepers[markets[0]]

        def print_bidlist(bids, keeper_bids):
            for bid, k_bid in zip(bids, keeper_bids):
                style = self.style.SUCCESS if bid.price == k_bid.price and bid.size == k_bid.size else self.style.ERROR
                size_format = f'{bid.size:,.5f}' if bid.size == k_bid.size else f'{bid.size:,.5f} {k_bid.size:,.5f}'
                delta = datetime.now() - bid.updated
                self.stdout.write(style(f'{bid.price:,.2f} {k_bid.price:,.2f}\t{size_format}\t[{delta.seconds}s]'))
        start = time.time()
        while True:
            try:
                health = { k.market.exchange_name: k.state for k in agg.keepers.values() }
                qsize = f'{agg.queue.qsize()} ({agg.updates_count})'
                bids, asks = agg.book.get_depth(count=5, depth=1)
                #bids, asks = k.book.get_best(count=10)
                print(f'\nBids ({len(agg.book.bids.values())}):')
                print_bidlist(bids, kep.book.bids)
                print(f'\nPrice: {agg.get_price():,.2f}')
                print(f'\nAsks ({len(agg.book.asks.values())}):')
                print_bidlist(asks, kep.book.asks)
                print(f'\nQueue: {qsize}')
                print()
                for market, state in health.items():
                    print(f'{market}\t{state}')
                time.sleep(1)
            except KeyboardInterrupt:
                agg.stop()
                break
            if time.time() - start > 1200:
                agg.stop()
