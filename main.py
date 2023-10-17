from datetime import datetime, timedelta
import json
import time
import pytz
from markets import get_market
from strategy import get_strategy
from livetest import LiveLoop
from datalayer import get_user

"""
config = json.load(open('api.json'))['KUCOIN']
market = get_market('KUCOIN', config)
response = market.user.get_base_fee()
pprint(response)
"""
user = get_user('master')
mc = json.load(open('api.json', 'r'))['BINANCE-TESTNET']
ll = LiveLoop(
    symbol='SOL-USDT',
    market=get_market('BINANCE', mc),
    strategy=get_strategy('v1')(),
    capital_limit=100.,
    asset_limit=1000.,
    initiating_user=user,
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
    initiating_user=user,
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

