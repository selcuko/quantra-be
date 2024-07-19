from datetime import datetime
import json
import time
import traceback
from quantapi.models import Market, MarketSymbol

from orderpulse.keeper import KeeperPool

market = Market.objects.get(exchange_name='MEXC')
market.get_interface()
symbol = MarketSymbol.objects.get(name='BTC-USDT', market=market)
k = KeeperPool.get(symbol)
k.start()

def print_bidlist(bids):
    for bid in bids:
        delta = datetime.now() - bid.updated
        print(f'{bid.price:,.2f}\t{bid.size:8,.5f}\t[{delta.seconds}s]')

while True:
    try:
        bids, asks = k.book.get_depth(count=5, depth=1)
        #bids, asks = k.book.get_best(count=10)
        print(f'\nBids ({len(k.book.bids.values())}):')
        print_bidlist(bids)
        print(f'\nPrice: {k.book.get_price():,.2f}')
        print(f'\nAsks ({len(k.book.asks.values())}):')
        print_bidlist(asks)
        time.sleep(1)
    except Exception as e:
        traceback.print_exc()
