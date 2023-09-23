import json
from pprint import pprint
from markets import get_market
from strategy import get_strategy
from livetest import run_livetest_in_sandbox



config = json.load(open('api.json'))['BINANCE-TESTNET']
market = get_market('BINANCE', config)
strategy = get_strategy('v1')()
order = market.place_market_order('BTC-USDT', 'sell', funds=50)
#pprint(order.json())
"""run_livetest_in_sandbox(
    'XRP-USDT', 
    market,
    strategy, 
    freq='1 min',
    capital=100
)"""