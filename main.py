import json
import time
from datetime import datetime, timedelta

import pytz

from logger import logger
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

ll2 = LiveLoop(
    symbol='DOGE-USDT',
    market=get_market('BINANCE', mc),
    strategy=get_strategy('v1')(),
    capital_limit=100.,
    asset_limit=1000.,
    freq='1 min',
    end=datetime.now(tz=pytz.UTC) + timedelta(days=1), 
)

ll3 = LiveLoop(
    symbol='XRP-USDT',
    market=get_market('BINANCE', mc),
    strategy=get_strategy('v1')(),
    capital_limit=100.,
    asset_limit=1000.,
    freq='1 min',
    end=datetime.now(tz=pytz.UTC) + timedelta(days=1), 
)

ll.run()
ll2.run()
ll3.run()
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    ll.stop()
    ll2.stop()
    logger.info('KeyboardInterrupt detected, shutting down gracefully')


