import json
from pprint import pprint
from markets import get_market

config = json.load(open('api.json'))['KUCOIN']
market = get_market('kucoin', config)
symbol = 'SUI-USDT'
order_id = market.place_market_order(symbol, 'buy', 1, remark='kucoin testing')
order = market.get_order(order_id)
pprint(order)
