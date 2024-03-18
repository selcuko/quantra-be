

from datetime import timedelta
from typing import Callable

import pytz

from models import interval_to_minutes


def get_start_end_dates(ts, interval):
    if interval < 60:
        start = ts.replace(minute=ts.minute - ts.minute % interval, second=0, microsecond=0)
        end = start + timedelta(minutes=interval)
    elif interval >= 1440:
        start = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    else:
        start = ts.replace(minute=0, second=0, microsecond=0)
        end = start + timedelta(minutes=interval)
        if end.hour == 0 and end.minute == 0:  # Handle end of day case
            end = end.replace(day=end.day + 1)
    return start, end


class MatchEngine:
    def __init__(self, interval:str, callback:Callable):
        self.price = None
        self.candle = {}
        self.interval = interval_to_minutes(interval)
        self.callback = callback

    def update_candle(self, data):
        ts = data.get('time').astimezone(pytz.UTC).replace(second=0, microsecond=0)
        vol = data['size'] * data['price']
        price = data['price']
        maker = data.get('maker', None)

        if self.candle and ts >= self.candle['end']:
            self.callback(self.candle)
            self.candle = {}
        if not self.candle.get('time'):
            start, end = get_start_end_dates(ts, self.interval)
            self.candle['time'] = start
            self.candle['open'] = price
            self.candle['high'] = price
            self.candle['low'] = price
            self.candle['volume'] = vol
            self.candle['start'] = start
            self.candle['end'] = end
            if maker:
                self.candle['buy_vol'] = vol
                self.candle['buy_count'] = 1
            elif maker is False:
                self.candle['sell_vol'] = vol
                self.candle['sell_count'] = 1
        else:
            self.candle['high'] = max(self.candle['high'], price)
            self.candle['low'] = min(self.candle['low'], price)
            self.candle['close'] = price
            self.candle['volume'] += vol
            self.candle['buy_vol'] = self.candle.get('buy_vol', 0)
            self.candle['buy_count'] = self.candle.get('buy_count', 0)
            self.candle['sell_vol'] = self.candle.get('sell_vol', 0)
            self.candle['sell_count'] = self.candle.get('sell_count', 0)
            if maker:
                self.candle['buy_vol'] += vol
                self.candle['buy_count'] += 1
            elif maker is False:
                self.candle['sell_vol'] += vol
                self.candle['sell_count'] += 1

    def on_match(self, data):
        self.update_candle(data)


 
