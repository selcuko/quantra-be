from datetime import datetime
import time
from django.core.management.base import BaseCommand

from orderpulse.keeper import KeeperPool
from orderpulse.structures import Book
from quantapi.models import MarketSymbol


class Command(BaseCommand):

    def handle(self, *args, **options):
        buffer = []
        book_sync = None

        def callback(delta):
            if not book_sync:
                buffer.append(delta)
                return
            if buffer:
                for d in buffer:
                    Book.apply(book_sync, d)
                buffer.clear()
            Book.apply(book_sync, delta)

            bids, asks = book_sync.get_best(count=1)
            print(f'Bids: {bids[0].price:,.2f} {bids[0].size:,.5f}', end='\t')
            print(f'Asks: {asks[0].price:,.2f} {asks[0].size:,.5f}')

        symbol = MarketSymbol.objects.get(contract_type=MarketSymbol.ContractType.SPOT, market__exchange_name='OKX', name='BTC-USDT')
        keeper = KeeperPool.get(symbol)
        keeper.add_callback(callback)
        keeper.start()

        book_sync = keeper.snapshot()

        while True:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                break