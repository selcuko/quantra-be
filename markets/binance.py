import math
import time
import uuid
from binance.client import Client
from datetime import datetime, timedelta
from logger import logger

from models import interval_to_minutes


class BinanceMarket:
    name = 'BINANCE'
    def __init__(self, config={}):
        self.authenticated = False
        if config:
            self.authenticated = True
        try:
            if self.authenticated:
                self.client = Client(
                    api_key=config['API_KEY'],
                    api_secret=config['API_SECRET'],
                    testnet=config['TESTNET']
                )
            else:
                self.client = Client()
        except Exception as e:
            logger.error(f'Error while initializing {self.name}')
            logger.exception(e)
            raise
        self.symbols = self.get_symbols()
    
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
    
    def _round_price(self, symbol, price):
        if not self.symbols[symbol]['isSpotTradingAllowed']:
            raise ValueError(f'Spot trading is not enabled for {symbol} on {self.name}')
        filters = self.symbols[symbol]['filters']
        price_filter = [f for f in filters if f['filterType'] == 'PRICE_FILTER'][0]
        if price > float(price_filter['maxPrice']):
            raise ValueError(f'Price {price} is greater than maxPrice {price_filter["maxPrice"]} for {symbol} on {self.name}')
        if price < float(price_filter['minPrice']):
            raise ValueError(f'Price {price} is less than minPrice {price_filter["minPrice"]} for {symbol} on {self.name}')
        notional_filter = [f for f in filters if f['filterType'] == 'NOTIONAL'][0]
        if price > float(notional_filter['maxNotional']):
            raise ValueError(f'Price {price} is greater than maxNotional {notional_filter["maxNotional"]} for {symbol} on {self.name}')
        if price < float(notional_filter['minNotional']):
            raise ValueError(f'Price {price} is less than minNotional {notional_filter["minNotional"]} for {symbol} on {self.name}')
        increment = float(price_filter['tickSize'])
        return math.floor(price / increment) * increment

    def place_market_order(self, symbol, side, funds=None, quantity=None):
        client_oid = uuid.uuid4().hex
        if not self.authenticated:
            raise ValueError(f'You must provide an API config to place orders on {self.name}')
        if not funds and not quantity:
            raise ValueError(f'You must provide either funds or quantity to place a market order on {self.name}')
        if funds and quantity:
            raise ValueError(f'You can only provide either funds or quantity to place a market order on {self.name}')
        try:
            funds = self._round_price(symbol, funds)
            order = self.client.order_market(side=side, symbol=self._format_symbol(symbol), quantity=quantity, quoteOrderQty=funds, newClientOrderId=client_oid)
            return order['orderId']
        except:
            logger.error(f'Error while placing market order on {self.name}', exc_info=True)
            raise
    
    def place_limit_order(self, symbol, side, price, size):
        symbol = self._format_symbol(symbol)
        client_oid = uuid.uuid4().hex
        if not self.authenticated:
            raise ValueError(f'You must provide an API config to place orders on {self.name}')
        try:
            price = self._round_price(symbol, price)
            order = self.client.order_limit(side=side, symbol=symbol, price=price, quantity=size, newClientOrderId=client_oid)
            return order['orderId']
        except:
            logger.error(f'Error while placing limit order on {self.name}', exc_info=True)
            raise
    
    def get_order(self, symbol, order_id):
        symbol = self._format_symbol(symbol)
        if not self.authenticated:
            raise ValueError(f'You must provide an API config to get orders on {self.name}')
        try:
            order = self.client.get_order(symbol=symbol, orderId=order_id)
            return order
        except:
            logger.error(f'Error while getting order on {self.name}', exc_info=True)
            raise
    
    def get_order_list(self, symbol, limit=100):
        symbol = self._format_symbol(symbol)
        if not self.authenticated:
            raise ValueError(f'You must provide an API config to get orders on {self.name}')
        try:
            orders = self.client.get_all_orders(symbol=symbol, limit=limit)
            return orders
        except:
            logger.error(f'Error while getting order list on {self.name}', exc_info=True)
            raise
    
    def get_open_orders(self, symbol=None):
        if not self.authenticated:
            raise ValueError(f'You must provide an API config to get orders on {self.name}')
        try:
            if symbol:
                symbol = self._format_symbol(symbol)
                orders = self.client.get_open_orders(symbol=symbol)
            else:
                orders = self.client.get_open_orders()
            return orders
        except:
            logger.error(f'Error while getting open orders on {self.name}', exc_info=True)
            raise

    def cancel_order(self, symbol, order_id):
        symbol = self._format_symbol(symbol)
        if not self.authenticated:
            raise ValueError(f'You must provide an API config to cancel orders on {self.name}')
        try:
            order = self.client.cancel_order(symbol=symbol, orderId=order_id)
            return order
        except:
            logger.error(f'Error while canceling order on {self.name}', exc_info=True)
            raise
    
    def cancel_all_orders(self, symbol=None):
        if not self.authenticated:
            raise ValueError(f'You must provide an API config to cancel orders on {self.name}')
        try:
            if symbol:
                symbol = self._format_symbol(symbol)
                orders = self.client.cancel_open_orders(symbol=symbol)
            else:
                orders = self.client.cancel_open_orders()
            return orders
        except:
            logger.error(f'Error while canceling all orders on {self.name}', exc_info=True)
            raise
    
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
                time.sleep(1)
                return self._get_klines(symbol, interval, start, end, limit, retry-1)
            raise
        return self._standardize_klines(klines)
    
    def get_symbols(self):
        return { self._standardize_symbol(symbol): symbol for symbol in self.client.get_exchange_info()['symbols']}
    
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
        
