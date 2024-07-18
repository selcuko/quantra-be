from datetime import datetime
import json
import time
import traceback
from django.core.management.base import BaseCommand, CommandError
from quantapi.models import Market, MarketSymbol, MarketAccount

from orderpulse.keeper import BookKeeper

def callback(update):
    with open('book.log', 'a') as f:
        f.write(json.dumps(update, default=str) + '\n')

market = Market.objects.get(exchange_name='MEXC')
symbol = MarketSymbol.objects.get(name='BTC-USDT', market=market)
account = MarketAccount.objects.filter(market=market).first()
if not account:
    raise CommandError('No account found for market')
k = BookKeeper(symbol, account, callback)
k.start()

def print_bidlist(bids):
    for bid in bids:
        delta = datetime.now() - bid.updated
        print(f'{bid.price:,.2f}\t{bid.size:8,.5f}\t[{delta.seconds}s]')

while True:
    try:
        bids, asks = k.book.get_depth(count=10, depth=10)
        #bids, asks = k.book.get_best(count=10)
        print(f'\nBids ({len(k.book.bids.values())}):')
        print_bidlist(bids)
        print('\nPrice:', k.book.get_price())
        print(f'\nAsks ({len(k.book.asks.values())}):')
        print_bidlist(asks)
        time.sleep(1)
    except Exception as e:
        traceback.print_exc()
