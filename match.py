

from datetime import datetime
from decimal import Decimal
from typing import Callable

import pytz

from models import interval_to_minutes


def get_start_end_dates(ts, interval):
    if interval < 60:
        start = ts.replace(minute=ts.minute - ts.minute % interval, second=0, microsecond=0)
        try:
            end = start.replace(minute=start.minute + interval)
        except ValueError:
            end = start.replace(hour=start.hour + 1, minute=(start.minute + interval) % 60)
    else:
        start = ts.replace(minute=0, second=0, microsecond=0)
        end = start.replace(hour=start.hour + interval // 60)
    return start, end


class MatchEngine:
    def __init__(self, interval:str, callback:Callable):
        self.price = None
        self.candle = {}
        self.interval = interval_to_minutes(interval)
        self.callback = callback

    def update_candle(self, data):
        ts = datetime.fromtimestamp(int(data['time']) / 1000000000, pytz.UTC).replace(second=0, microsecond=0)
        vol = float(Decimal(data['size']) * Decimal(data['price']))
        price = float(data['price'])

        if self.candle and ts < self.candle['end']:
            self.callback(self.candle)
            self.candle = {}
        if not self.candle:
            start, end = get_start_end_dates(ts, self.interval)
            self.candle['time'] = start
            self.candle['open'] = price
            self.candle['high'] = price
            self.candle['low'] = price
            self.candle['volume'] = vol
            self.candle['start'] = start
            self.candle['end'] = end
        else:
            self.candle['high'] = max(self.candle['high'], price)
            self.candle['low'] = min(self.candle['low'], price)
            self.candle['close'] = price
            self.candle['volume'] += vol

    def on_match(self, data):
        self.update_candle(data)


 
