import json
from pprint import pprint
from markets import get_market
from strategy import get_strategy
from livetest import run_livetest_in_sandbox



config = json.load(open('api.json'))['KUCOIN']
market = get_market('KUCOIN', config)
strategy = get_strategy('v1')


order = market.place_market_order('SUI-USDT', 'sell', quantity=0.179112321)
print('RAW', order)
order.refresh()
print('REFRESHED', order)
print('JSON', order.json())
