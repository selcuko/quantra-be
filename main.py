import json
from pprint import pprint
from markets import get_market
from strategy import get_strategy
from livetest import run_livetest_in_sandbox



config = json.load(open('api.json'))['BINANCE-TESTNET']
market = get_market('BINANCE', config)
strategy = get_strategy('v1')
symbol = 'BTC-USDT'
#order = market.place_limit_order(symbol, 'buy', price=26000, quantity=0.01)
order = market.place_market_order(symbol, 'buy', funds=100)
client_oid = order.client_oid
response = market.cancel_order(symbol, order)
print(order)
print(response)