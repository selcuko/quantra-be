import time
from binance.client import Client
from datetime import datetime, timedelta
from logger import logger
from joblib import Memory

from models import interval_to_minutes

memory = Memory('cache', verbose=5)

class BinanceMarket:
    name = 'BINANCE'
    def __init__(self, config):
        self.authenticated = False
        if config:
            self.authenticated = True
        try:
            self.client = Client()
        except Exception as e:
            logger.error(f'Error while initializing {self.name}')
            logger.exception(e)
            raise
    
    def _standardize_klines(self, klines):
        return [[ datetime.fromtimestamp(int(kline[0]) // 1000).replace(second=0, microsecond=0),
                  float(kline[1]),
                  float(kline[2]),
                  float(kline[3]),
                  float(kline[4]),
                  float(kline[5]),
                ] for kline in klines ]  
    
    def _standardize_symbol(self, symbol):
        return f'{symbol["baseAsset"]}-{symbol["quoteAsset"]}'

    def _format_symbol(self, symbol):
        assert '-' in symbol, f'Symbol must be in the format BASE-QUOTE, you provided:{symbol}'
        symbol = symbol.replace('-', '').upper()
        return symbol

    def _format_interval(self, interval):
        return {
            '1 min': Client.KLINE_INTERVAL_1MINUTE,
            '3 min': Client.KLINE_INTERVAL_3MINUTE,
            '5 min': Client.KLINE_INTERVAL_5MINUTE,
            '15 min': Client.KLINE_INTERVAL_15MINUTE,
            '30 min': Client.KLINE_INTERVAL_30MINUTE,
            '1 hour': Client.KLINE_INTERVAL_1HOUR,
            '2 hour': Client.KLINE_INTERVAL_2HOUR,
            '4 hour': Client.KLINE_INTERVAL_4HOUR,
            '6 hour': Client.KLINE_INTERVAL_6HOUR,
            '8 hour': Client.KLINE_INTERVAL_8HOUR,
            '12 hour': Client.KLINE_INTERVAL_12HOUR,
            '1 day': Client.KLINE_INTERVAL_1DAY,
            '3 day': Client.KLINE_INTERVAL_3DAY,
            '1 week': Client.KLINE_INTERVAL_1WEEK,
            '1 month': Client.KLINE_INTERVAL_1MONTH,
        }[interval]

    def _format_datetime(self, dt):
        return str(dt.timestamp())
    
    def get_klines(self, symbol, interval, start:datetime, end:datetime=None, limit=1000):
        start = start.replace(second=0, microsecond=0)
        #return memory.cache(self._get_klines, ignore=['self'])(symbol, interval, start, limit)
        return self._get_klines(symbol, interval, start, end, limit)

    def _get_klines(self, symbol, interval, start:datetime, end:datetime=None, limit=1000, retry=3):
        if end:
            logger.debug('param:end specified while fetching klines, ignoring param:limit')
            calculated_end = end
        else:
            calculated_end = start + timedelta(minutes=interval_to_minutes(interval) * limit)
        try:
            logger.debug(f'Hitting Binance API for {symbol} at {start} -> {calculated_end} with limit {limit}')
            klines = self.client.get_historical_klines(
                        symbol=self._format_symbol(symbol), 
                        interval=self._format_interval(interval), 
                        start_str=self._format_datetime(start),
                        end_str=str(calculated_end),
                        limit=limit
                    )
        except:
            logger.error(f'Error while fetching klines for {symbol} from {self.name}', exc_info=True)
            if retry > 0:
                logger.warning(f'Retrying {retry} more times')
                time.sleep(3)
                return self._get_klines(symbol, interval, start, end, limit, retry-1)
            raise
        return self._standardize_klines(klines)
    
    def get_symbols(self):
        symbol_list = [ symbol for symbol in self.client.get_exchange_info()['symbols'] ]
        symbol_list = [ self._standardize_symbol(symbol) for symbol in symbol_list if symbol['quoteAsset'] == 'USDT' ]
        return sorted(symbol_list)
        
    def can_trade_on_symbol(self, symbol):
        self.symbols = self.get_symbols()
        return symbol in self.symbols
    
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
        
