import json
from pprint import pprint
from markets import get_market
from strategy import get_strategy
from livetest import run_livetest_in_sandbox



config = json.load(open('api.json'))['KUCOIN']
market = get_market('KUCOIN', config)
response = market.user.get_base_fee()
pprint(response)
