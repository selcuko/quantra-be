# websocket approach to market data
# we will be generation our own candles

import asyncio
import pytz
from websockets.sync.client import connect
import json
import logging
import os
import time
import traceback
from datetime import datetime
import sys
import random
from binance.client import Client
from binance.client import AsyncClient

from liveloop import LiveLoop
from quantapi.models import Market
from strategy import get_strategy

ws_uri = "wss://stream.binance.com:9443/ws/btcusdt@kline_1m"

def format_ws_candle(payload):
    candle = payload['k']
    return {
        'time': datetime.fromtimestamp(candle['t']/1000, tz=pytz.UTC).replace(second=0, microsecond=0),
        'start': candle['t'],
        'end': candle['T'],
        'open': float(candle['o']),
        'high': float(candle['h']),
        'low': float(candle['l']),
        'close': float(candle['c']),
        'volume': float(candle['v']),
        'trades': int(candle['n']),
        'last': candle['x'],
        'quote_asset_volume': float(candle['q']),
        'taker_buy_base_asset_volume': float(candle['V']),
        'taker_buy_quote_asset_volume': float(candle['Q']),
    }

ws = connect(ws_uri)
ll = LiveLoop(
    'BTC-USDT',
    Market.objects.get(exchange_name='BINANCE', mainnet_enabled=False),
    get_strategy('v1')(),
    10,
    0,
    '1 min'
)
ll.precheck()
print("connected")
while True:
    try:
        payload_str = ws.recv()
        payload = json.loads(payload_str)
        candle = format_ws_candle(payload)
        if candle['last']:
            print('\n', candle)
            ll.on_candle(candle)
        else:
            print('.', end='', flush=True)

    except Exception as e:
        print(e)
        traceback.print_exc()
        break
