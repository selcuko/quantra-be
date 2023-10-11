from datetime import datetime, timedelta
import time
import pytz
import requests
from logger import logger
from models import interval_to_minutes

class MEXCMarket:
    name = 'MEXC'
    def __init__(self, config) -> None:
        self.authenticated = False
        if config:
            self.authenticated = True
        self.url = 'https://api.mexc.com'
    
    def _standardize_klines(self, klines):
        klines = [[ datetime.fromtimestamp(int(kline[0]) // 1000, tz=pytz.UTC).replace(second=0, microsecond=0),
                  float(kline[1]),
                  float(kline[2]),
                  float(kline[3]),
                  float(kline[4]),
                  float(kline[5]),
                ] for kline in klines ]
        return klines
    
    def _standardize_symbol(self, symbol):
        return symbol.replace('USDT', '-USDT')
    
    def _format_symbol(self, symbol):
        assert '-' in symbol, f'Symbol must be in the format BASE-QUOTE, you provided:{symbol}'
        return symbol.replace('-', '').upper()
    
    def _format_interval(self, interval):
        return {
            '1 min': '1m',
            '3 min': '3m',
            '5 min': '5m',
            '15 min': '15m',
            '30 min': '30m',
            '1 hour': '1h',
            '2 hour': '2h',
            '4 hour': '4h',
            '6 hour': '6h',
            '8 hour': '8h',
            '12 hour': '12h',
            '1 day': '1d',
            '3 day': '3d',
            '1 week': '1w',
            '1 month': '1M',
        }[interval]
    
    def _format_datetime(self, dt):
        return int(dt.timestamp()*1000)
    
    def get_klines(self, symbol, interval, start=None, end=None, limit=1000):
        return self._get_klines(symbol, interval, start, end, limit)
    
    def _get_klines(self, symbol, interval, start=None, end=None, limit=1000, retry=3):
        if not end and not start:
            raise ValueError('Either start or end must be provided')
        if not limit or limit > 1000:
            logger.warning(f'MEXC only allows a maximum of 1000 klines per request, you requested {limit}')
            limit = 1000
        calculated_timerange = timedelta(minutes=interval_to_minutes(interval) * limit)
        if not start:
            start = end - calculated_timerange
        elif not end:
            end = start + calculated_timerange
        else:
            if end - start > calculated_timerange:
                # calculate how many candles are in the timerange
                candles_in_timerange = (end - start) // timedelta(minutes=interval_to_minutes(interval))
                raise ValueError(f'We can get a maximum of 1000 klines per request (limit={limit}), your timerange is too wide ({candles_in_timerange} candles), please reduce the timerange or increase the interval')
        try:
            uri = f'{self.url}/api/v3/klines?symbol={self._format_symbol(symbol)}&interval={self._format_interval(interval)}&limit={limit}&startTime={self._format_datetime(start)}&endTime={self._format_datetime(end)}'
            logger.debug(f'Hitting MEXC API for {symbol} at {start} -> {end} with limit {limit} ({uri})')
            response = requests.get(uri)
            response.raise_for_status()
            kline_data = response.json()
        except:
            logger.error(f'Error while fetching klines for {self.name}', exc_info=True)
            if retry > 0:
                logger.warning(f'Retrying {retry} more times')
                time.sleep(1)
                return self._get_klines(symbol, interval, start, end, limit, retry-1)
            raise
        if not kline_data or not isinstance(kline_data, list) or not isinstance(kline_data[0], list):
            return []
        return self._standardize_klines(kline_data)

    def get_symbols(self):
        try:
            uri = f'{self.url}/api/v3/exchangeInfo'
            logger.debug(f'Hitting MEXC API for symbols ({uri})')
            response = requests.get(uri)
            response.raise_for_status()
            symbols = response.json()
        except:
            logger.error(f'Error while fetching symbols for {self.name}', exc_info=True)
            raise
        symbol_list = [ symbol['symbol'] for symbol in symbols['symbols'] if symbol['quoteAsset'] == 'USDT' ]
        symbol_list = [ self._standardize_symbol(symbol) for symbol in symbol_list ]
        return sorted(symbol_list)
    
    def can_trade_on_symbol(self, symbol):
        return symbol in self.get_symbols()
    
    def get_last_klines(self, symbol, interval, limit=100):
        minutes = interval_to_minutes(interval)
        now = datetime.now(tz=pytz.UTC)
        start = now - timedelta(minutes=minutes*limit)
        klines = self.get_klines(symbol, interval, start, now)
        last_kline_dt = klines[-1][0]
        if (now - last_kline_dt) > timedelta(minutes=minutes):
            error = f'Last kline dt {last_kline_dt} does not match current time {now}, total klines: {len(klines)}, {start} -> {now}'
            logger.warning(error)
            raise Exception(error)
        return klines