from datetime import datetime, timedelta
import time
from kucoin.client import Market
from logger import logger
from models import interval_to_minutes

class KucoinMarket:
    name = 'KUCOIN'
    def __init__(self, config) -> None:
        self.authenticated = False
        if config:
            self.authenticated = True
        try:
            self.client = Market()
        except Exception as e:
            logger.error(f'Error while initializing {self.name}', exc_info=True)
            raise
    
    def _standardize_klines(self, klines):
        klines = reversed(klines)
        return [[ datetime.fromtimestamp(int(kline[0])).replace(second=0, microsecond=0),
                    float(kline[1]),
                    float(kline[2]),
                    float(kline[3]),
                    float(kline[4]),
                    float(kline[5]),
                ] for kline in klines ]
    
    def _standardize_symbol(self, symbol):
        return symbol
    
    def _format_symbol(self, symbol):
        return symbol
    
    def _format_interval(self, interval):
        return interval.replace(' ', '')
    
    def _format_datetime(self, dt):
        return int(dt.timestamp())
    
    def get_klines(self, symbol, interval, start=None, end=None, limit=1000):
        return self._get_klines(symbol, interval, start, end, limit)
    
    def _get_klines(self, symbol, interval, start=None, end=None, limit=1000, retry=3):
        if not start and not end:
            raise ValueError('Either start or end must be provided')
        if limit > 1000:
            logger.warning(f'Kucoin only allows a maximum of 1000 klines per request, you requested {limit}')
            limit = 1000
        calculated_timerange = timedelta(minutes=interval_to_minutes(interval) * limit)
        if not start:
            start = end - calculated_timerange
        elif not end:
            end = start + calculated_timerange
        else:
            if end - start > calculated_timerange:
                # calculate how many candles are in the timerange
                candles_in_timerange = (end - start) / timedelta(minutes=interval_to_minutes(interval))
                raise ValueError(f'We can get a maximum of 1000 klines per request, your timerange is too wide ({candles_in_timerange} candles), please reduce the timerange or increase the interval')
        try:
            logger.debug('Hitting Kucoin API for {symbol} at {start} -> {end} with limit {limit}')
            klines = self.client.get_kline(
                symbol=self._format_symbol(symbol),
                kline_type=self._format_interval(interval),
                startAt=self._format_datetime(start),
                endAt=self._format_datetime(end),
                limit=limit
            )
        except:
            logger.error(f'Error while fetching klines for {symbol} from {self.name}', exc_info=True)
            if retry > 0:
                logger.warning(f'Retrying {retry} more times')
                time.sleep(1)
                return self._get_klines(symbol, interval, start, end, limit, retry-1)
            raise
        return self._standardize_klines(klines)

    def get_symbols(self):
        symbol_list = [ symbol['symbol'] for symbol in self.client.get_symbol_list_v2() ]
        symbol_list = [ self._standardize_symbol(symbol) for symbol in symbol_list if symbol.endswith('USDT') ]
        return sorted(symbol_list)

    def can_trade_on_symbol(self, symbol):
        return symbol in self.get_symbols()
    
    def get_last_klines(self, symbol, interval, limit=100):
        minutes = interval_to_minutes(interval)
        now = datetime.now()
        start = now - timedelta(minutes=minutes*limit)
        klines = self.get_klines(symbol, interval, start, now)
        last_kline_dt = klines[-1][0]
        if (now - last_kline_dt) > timedelta(minutes=minutes):
            error = f'Last kline dt {last_kline_dt} does not match current time {now}, total klines: {len(klines)}, {start} -> {now}'
            logger.warning(error)
            raise Exception(error)
        return klines