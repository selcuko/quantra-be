from datetime import datetime
import time
from django.core.management.base import BaseCommand
from orderpulse.consolidator import AggregatorPool


class Command(BaseCommand):
    def handle(self, *args, **options):
        markets = ['MEXC', 'KUCOIN', 'GATEIO', 'BYBIT', 'OKX', 'BINANCE'] 
        agg = AggregatorPool.get('BTC-USDT', markets)

        def print_bidlist(bids):
            for bid in bids:
                delta = datetime.now() - bid.updated
                print(f'{bid.price:,.2f}\t{bid.size:8,.5f}\t[{delta.seconds}s]')
        start = time.time()
        while True:
            health = { k.market.exchange_name: k.state for k in agg.keepers.values() }
            qsize = f'{agg.qsize.value} ({agg.updates_count})'
            bids, asks = agg.book.get_depth(count=5, depth=100)
            #bids, asks = k.book.get_best(count=10)
            print(f'\nBids ({len(agg.book.bids.values())}):')
            print_bidlist(bids)
            print(f'\nPrice: {agg.get_price():,.2f}')
            print(f'\nAsks ({len(agg.book.asks.values())}):')
            print_bidlist(asks)
            print(f'\nQueue: {qsize}')
            print()
            for market, state in health.items():
                print(f'{market}\t{state}')
            time.sleep(1)
            
            if time.time() - start > 120:
                agg.stop()
