import json
from pprint import pprint
from markets import get_market
from strategy import get_strategy
from livetest import run_livetest_in_sandbox

config = json.load(open('api.json'))['BINANCE-TESTNET']
market = get_market('BINANCE', config)
strategy = get_strategy('v1')
symbol = 'BTC-USDT'
order_id = market.place_market_order(symbol, 'buy', funds=100)
order = market.get_order(symbol, order_id)
print('\nSEP\n')
pprint(order)