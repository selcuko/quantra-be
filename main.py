import json
from pprint import pprint
from markets import get_market
from strategy import get_strategy
from livetest import run_livetest_in_sandbox

config = json.load(open('api.json'))['BINANCE-TESTNET']
strategy = get_strategy('v1')()
run_livetest_in_sandbox('XRP-USDT', 'BINANCE', config, strategy, freq='1 min')
