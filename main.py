import json
import time
from datetime import datetime, timedelta

import pytz

from livetest import LiveLoop
from markets import get_market
from strategy import get_strategy

"""
config = json.load(open('api.json'))['KUCOIN']
market = get_market('KUCOIN', config)
response = market.user.get_base_fee()
pprint(response)
"""
mc = json.load(open('api.json', 'r'))['BINANCE-TESTNET']
ll = LiveLoop(
    symbol='SOL-USDT',
    market=get_market('BINANCE', mc),
    strategy=get_strategy('v1')(),
    capital_limit=100.,
    asset_limit=1000.,
    freq='1 min',
    end=datetime.now(tz=pytz.UTC) + timedelta(days=1), 
)
ll.run()

ll2 = LiveLoop(
    symbol='DOGE-USDT',
    market=get_market('BINANCE', mc),
    strategy=get_strategy('v1')(),
    capital_limit=100.,
    asset_limit=1000.,
    freq='1 min',
    end=datetime.now(tz=pytz.UTC) + timedelta(days=1), 
)
ll2.run()
time.sleep(15)
ll.stop()
time.sleep(100)
ll2.stop()

ll.idle()
ll2.idle()

