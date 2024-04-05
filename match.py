

from datetime import timedelta
from typing import Callable
from django.utils import timezone
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
        self.candle_started_processing = timezone.now()
        self.last_price = None
        self.last_price_ts = None

    def close_candle(self, corrupt=False):
        self.candle_started_processing = timezone.now()
        self.candle['corrupt'] = self.candle.get('corrupt', False) or corrupt  # if already corrupt, keep it corrupt
        self.callback(self.candle)
        self.candle = {}

    def update_candle(self, data):
        ts = data.get('time').astimezone(pytz.UTC).replace(second=0, microsecond=0)
        vol = data['size'] * data['price']
        self.last_price = price = data['price']
        self.last_price_ts = ts
        maker = data.get('maker', None)

        if self.candle and ts >= self.candle['end']:
            self.close_candle()

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
            if timezone.now() - self.candle['time'] > timedelta(minutes=self.interval // 3 if self.interval >= 3 else 3):
                # if we're more than 1/3 of the way through the candle, we flag it as corrupt (incomplete)
                self.candle['corrupt'] = True
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

            candle_deltatime = timezone.now() - self.candle_started_processing
            if candle_deltatime > timedelta(minutes=self.interval):
                # sanity check. force candle to close if it's been open longer than interval
                self.close_candle(corrupt=True)

    def on_match(self, data):
        self.update_candle(data)


if __name__ == '__main__':
    import django
    django.setup()
    from logger import logger
    from quantapi.models import Market
    def callback(candle):
        logger.info(f'CANDLE: {candle!s}')
    print('Fetching market...')
    market = Market.objects.get(exchange_name='BINANCE')
    print('Loading interface...')
    iface = market.get_interface()
    print('Initiating websocket connection...')
    iface.init_match_engine('AEVO-USDT', '15 min', print, None)

