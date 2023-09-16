from datetime import datetime, timedelta
import math
import time
import uuid
from kucoin.client import Market, Trade
from logger import logger
from models import interval_to_minutes

class KucoinMarket:
    name = 'KUCOIN'
    def __init__(self, config={}) -> None:
        self.authenticated = False
        if config:
            self.authenticated = True
        try:
            if self.authenticated:
                self.market = Market(
                    key=config['API_KEY'], 
                    secret=config['API_SECRET'], 
                    passphrase=config['API_PASSPHRASE'])
                self.trade = Trade(
                    key=config['API_KEY'], 
                    secret=config['API_SECRET'], 
                    passphrase=config['API_PASSPHRASE'])
            else:
                self.market = Market()
        except Exception as e:
            logger.error(f'Error while initializing {self.name}', exc_info=True)
            raise
        self.symbols = self.get_symbols()
    
    def _standardize_klines(self, klines):
        try:
            klines.reverse()
            return [[ datetime.fromtimestamp(int(kline[0])).replace(second=0, microsecond=0),
                        float(kline[1]),
                        float(kline[2]),
                        float(kline[3]),
                        float(kline[4]),
                        float(kline[5]),
                    ] for kline in klines ]
        except:
            logger.error(f'Error while standardizing klines for {self.name}: {klines}', exc_info=True)
            raise
    
    def _standardize_symbol(self, symbol):
        return symbol
    
    def _format_symbol(self, symbol):
        return symbol
    
    def _format_interval(self, interval):
        return interval.replace(' ', '')
    
    def _format_datetime(self, dt):
        return int(dt.timestamp())
    
    def _round_price(self, symbol, price):
        if not self.symbols[symbol]['enableTrading']:
            raise ValueError(f'Trading is not enabled for {symbol} on {self.name}')
        if price < float(self.symbols[symbol]['quoteMinSize']):
            raise ValueError(f'Price {price} is too low for {symbol}, minimum is {self.symbols[symbol]["quoteMinSize"]}')
        if price > float(self.symbols[symbol]['quoteMaxSize']):
            raise ValueError(f'Price {price} is too high for {symbol}, maximum is {self.symbols[symbol]["quoteMaxSize"]}')
        increment = float(self.symbols[symbol]['priceIncrement'])
        price = math.floor(price / increment) * increment
        return price

    def place_market_order(self, symbol, side, funds, remark=None):
        if not self.authenticated:
            raise ValueError(f'You must provide an API config to place orders on {self.name}')
        if remark and len(remark) > 100:
            raise ValueError('Remark must be less than 100 characters')
        client_oid = uuid.uuid4().hex
        response = self.trade.create_market_order(
            symbol=self._format_symbol(symbol),
            side=side,
            funds=funds,
            client_oid=client_oid
        )
        if not response:
            raise ValueError(f'Error while placing market order on {self.name}')
        return response.get('orderId')

    def place_limit_order(self, symbol, side, price, size, remark=None):
        if not self.authenticated:
            raise ValueError(f'You must provide an API config to place orders on {self.name}')
        if remark and len(remark) > 100:
            raise ValueError('Remark must be less than 100 characters')
        client_oid = uuid.uuid4().hex
        response = self.trade.create_limit_order(
            symbol=self._format_symbol(symbol),
            side=side,
            price=self._round_price(symbol, price),
            size=size,
            client_oid=client_oid,
            remark=remark
        )
        if not response:
            raise ValueError(f'Error while placing limit order on {self.name}')
        return response.get('orderId')

    def get_order(self, order_id):
        if not self.authenticated:
            raise ValueError(f'You must provide an API config to get orders on {self.name}')
        response = self.trade.get_order_details(orderId=order_id)
        if not response:
            raise ValueError(f'Error while fetching order {order_id} on {self.name}')
        return response
    
    def get_order_list(self, symbol=None, side=None, status='active'):
        if not self.authenticated:
            raise ValueError(f'You must provide an API config to get orders on {self.name}')
        response = self.trade.get_orders(symbol=symbol, side=side, status=status)
        if not response:
            raise ValueError(f'Error while fetching orders on {self.name}')
        return response

    def cancel_order(self, order_id):
        if not self.authenticated:
            raise ValueError(f'You must provide an API config to cancel orders on {self.name}')
        response = self.trade.cancel_order(orderOid=order_id)
        if not response:
            raise ValueError(f'Error while cancelling order {order_id} on {self.name}')
        if not response.get('cancelledOrderIds') == [order_id]:
            raise ValueError(f'Error while cancelling order {order_id} on {self.name}, cancelledOrderIds mismatch: {response.get("cancelledOrderIds")} != {order_id} ({response})')
        return order_id
    
    def cancel_all_orders(self, symbol=None):
        if not self.authenticated:
            raise ValueError(f'You must provide an API config to cancel orders on {self.name}')
        response = self.trade.cancel_all_orders(symbol=symbol)
        if not response:
            raise ValueError(f'Error while cancelling all orders on {self.name}')
        return response.get('cancelledOrderIds', [])

    def get_klines(self, symbol, interval, start=None, end=None, limit=1000, retry=0):
        return self._get_klines(symbol, interval, start, end, limit, retry)
    
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
                candles_in_timerange = (end - start) // timedelta(minutes=interval_to_minutes(interval))
                raise ValueError(f'We can get a maximum of 1000 klines per request, your timerange is too wide ({candles_in_timerange} candles), please reduce the timerange or increase the interval')
        try:
            logger.debug(f'Hitting Kucoin API for {symbol} at {start} -> {end} with limit {limit}')
            klines = self.market.get_kline(
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
        if not klines or not isinstance(klines, list) or not isinstance(klines[0], list):
            return []
        return self._standardize_klines(klines)

    def get_symbols(self):
        return { symbol['symbol']: symbol for symbol in self.market.get_symbol_list_v2()}
    
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