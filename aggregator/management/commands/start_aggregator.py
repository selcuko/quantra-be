from datetime import datetime
import json
import time
import traceback

from orderpulse.consolidator import BookAggregator

def callback(update):
    with open('book.log', 'a') as f:
        f.write(json.dumps(update, default=str) + '\n')

agg = BookAggregator('BTC-USDT')
markets = ['MEXC', 'KUCOIN', 'GATEIO', 'BYBIT', 'OKX', 'BINANCE']
agg.add_markets(markets)

def print_bidlist(bids):
    for bid in bids:
        delta = datetime.now() - bid.updated
        print(f'{bid.price:,.2f}\t{bid.size:8,.5f}\t[{delta.seconds}s]')

while True:
    try:
        health = { k.market.exchange_name: k.state for k in agg.keepers.values() }
        bids, asks = agg.book.get_depth(count=5, depth=1)
        #bids, asks = k.book.get_best(count=10)
        print(f'\nBids ({len(agg.book.bids.values())}):')
        print_bidlist(bids)
        print(f'\nPrice: {agg.get_price():,.2f}')
        print(f'\nAsks ({len(agg.book.asks.values())}):')
        print_bidlist(asks)
        print(f'\nHealth:', [f'{k}: {v}' for k, v in health.items()])
        time.sleep(1)
    except Exception as e:
        traceback.print_exc()
