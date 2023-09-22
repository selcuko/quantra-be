import math
import time
from typing import Literal
import uuid
from binance.client import Client
from datetime import datetime, timedelta
from logger import logger
from markets.helper import authentication_required
from models import ExchangeSymbol, Order, interval_to_minutes
from filters import LotFilter, PriceFilter, FundFilter


class BinanceMarket:
    name = 'BINANCE'
    def __init__(self, config={}):
        self.authenticated = bool(config.get('API_KEY') and config.get('API_SECRET'))
        try:
            if self.authenticated:
                self.client = Client(
                    api_key=config['API_KEY'],
                    api_secret=config['API_SECRET'],
                    testnet=config['TESTNET'])
            else:
                self.client = Client()
        except Exception as e:
            logger.error(f'Error while initializing {self.name}', exc_info=True)
            raise
        self.symbols = self.get_symbols()
        if self.authenticated:
            self.get_account()
        else:
            self.spot_trading_enabled = False
            self.assets = {}
            self.capital = 0
    
    def __str__(self) -> str:
        return f'{self.name} (Authenticated: {self.authenticated})'

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

    def _get_symbol_from_name(self, symbol_name:str):
        try:
            return self.symbols[symbol_name]
        except KeyError:
            logger.error(f'Symbol {symbol_name} is not present in {self.name}')
            raise ValueError(f'Symbol {symbol_name} is not present in {self.name}')

    @authentication_required
    def place_market_order(self, symbol:ExchangeSymbol, side:Literal['buy', 'sell'], funds:float=None, quantity:float=None) -> Order:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        client_oid = uuid.uuid4().hex
        if (not funds and not quantity) or (funds and quantity):
            raise ValueError(f'You must provide either funds or quantity to place a market order on {self.name}')
        try:
            logger.info(f'Placing market order on {self.name} for {symbol} with side {side} and funds {funds} and quantity {quantity}')
            order = self.client.order_market(
                side=side, 
                symbol=symbol.name, 
                quantity=quantity, 
                quoteOrderQty=funds, 
                newClientOrderId=client_oid)
            logger.info(f'Market order placed on {self.name} for {symbol} with side {side} and funds {funds} and quantity {quantity} with order id {order["orderId"]}')
            return self._prep_order(order, symbol)
        except:
            logger.error(f'Error while placing market order on {self.name}', exc_info=True)
            raise
    
    @authentication_required
    def place_limit_order(self, symbol:ExchangeSymbol, side:Literal['buy', 'sell'], price:float, quantity:float) -> Order:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        client_oid = uuid.uuid4().hex
        try:
            logger.info(f'Placing limit order on {self.name} for {symbol} with side {side} and price {price} and quantity {quantity}')
            order = self.client.order_limit(
                side=side, 
                symbol=symbol.name, 
                price=price, 
                quantity=quantity, 
                newClientOrderId=client_oid)
            logger.info(f'Limit order placed on {self.name} for {symbol} with side {side} and price {price} and quantity {quantity} with order id {order["orderId"]}')
            return self._prep_order(order, symbol)
        except:
            logger.error(f'Error while placing limit order on {self.name}', exc_info=True)
            raise
    
    @authentication_required
    def get_order(self, symbol:ExchangeSymbol, order_id:int) -> Order:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        if isinstance(order_id, Order):
            order_id = order_id.oid
        try:
            logger.info(f'Getting order {order_id} on {self.name} for {symbol}')
            order = self.client.get_order(symbol=symbol.name, orderId=order_id)
            return self._prep_order(order, symbol)
        except:
            logger.error(f'Error while getting order on {self.name}', exc_info=True)
            raise
    
    @authentication_required
    def get_orders(self, symbol:ExchangeSymbol) -> list[Order]:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        try:
            logger.info(f'Getting orders on {self.name} for {symbol}')
            orders = self.client.get_all_orders(symbol=symbol.name)
            return [self._prep_order(order, symbol) for order in orders]
        except:
            logger.error(f'Error while getting order list on {self.name}', exc_info=True)
            raise
    
    @authentication_required
    def get_open_orders(self, symbol:ExchangeSymbol=None) -> list[Order]:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        try:
            if symbol:
                logger.info(f'Getting open orders on {self.name} for {symbol}')
                orders = self.client.get_open_orders(symbol=symbol.name)
            else:
                logger.info(f'Getting open orders on {self.name}')
                orders = self.client.get_open_orders()
            return [self._prep_order(order, symbol) for order in orders]
        except:
            logger.error(f'Error while getting open orders on {self.name}', exc_info=True)
            raise

    @authentication_required
    def cancel_order(self, symbol:ExchangeSymbol, order_id:int) -> Order:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        if isinstance(order_id, Order):
            order_id = order_id.oid
        try:
            logger.info(f'Canceling order {order_id} on {self.name} for {symbol}')
            order = self.client.cancel_order(symbol=symbol.name, orderId=order_id)
            return self._prep_order(order, symbol)
        except Exception as e:
            if 'Unknown order sent' in str(e):
                logger.warning(f'Order {order_id} not found on {self.name}')
                return
            logger.error(f'Error while canceling order on {self.name}', exc_info=True)
            raise
    
    @authentication_required
    def cancel_all_orders(self, symbol:ExchangeSymbol=None) -> list[Order]:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        try:
            if symbol:
                logger.info(f'Canceling all orders on {self.name} for {symbol}')
                orders = self.client.cancel_open_orders(symbol=symbol.name)
            else:
                logger.info(f'Canceling all orders on {self.name}')
                orders = self.client.cancel_open_orders()
            return [self._prep_order(order, symbol) for order in orders]
        except:
            logger.error(f'Error while canceling all orders on {self.name}', exc_info=True)
            raise
    
    @authentication_required
    def get_account(self):
        logger.info(f'Getting account data on {self.name}')
        account = self.client.get_account()
        self.spot_trading_enabled = 'SPOT' in account.get('permissions', []) and account.get('canTrade')
        self.assets = { asset['asset']: float(asset['free']) for asset in account['balances'] }
        self.capital = self.assets.get('USDT', 0)
    
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
    
    def get_symbols(self) -> list[ExchangeSymbol]:
        return { self._standardize_symbol(symbol): self._prep_symbol(symbol) for symbol in self.client.get_exchange_info()['symbols']}

    def _prep_symbol(self, symbol:dict):
        exc_symbol = ExchangeSymbol(
                name = symbol['symbol'],
                base = symbol['baseAsset'],
                quote = symbol['quoteAsset'],
                base_precision = symbol['baseAssetPrecision'],
                quote_precision = symbol['quotePrecision'],
                spot_trading_enabled = symbol['isSpotTradingAllowed'],
                margin_trading_enabled = symbol['isMarginTradingAllowed'])
        if raw_price_filter := [filter for filter in symbol['filters'] if filter['filterType'] == 'PRICE_FILTER']:
            raw_price_filter = raw_price_filter[0]
            exc_symbol.filters.append(
                PriceFilter(
                    max_price=raw_price_filter.get('maxPrice'),
                    min_price=raw_price_filter.get('minPrice'),
                    tick_size=raw_price_filter.get('tickSize'),
                    ask_multiplier_up=raw_price_filter.get('askMultiplierUp'),
                    ask_multiplier_down=raw_price_filter.get('askMultiplierDown'),
                    bid_multiplier_up=raw_price_filter.get('bidMultiplierUp'),
                    bid_multiplier_down=raw_price_filter.get('bidMultiplierDown')
                    )
                )
        if raw_pct_price_filter := [filter for filter in symbol['filters'] if filter['filterType'] == 'PERCENT_PRICE_BY_SIDE']:
            raw_pct_price_filter = raw_pct_price_filter[0]
            exc_symbol.filters.append(
                PriceFilter(
                    max_price=raw_pct_price_filter.get('maxPrice'),
                    min_price=raw_pct_price_filter.get('minPrice'),
                    tick_size=raw_pct_price_filter.get('tickSize'),
                    ask_multiplier_up=raw_pct_price_filter.get('askMultiplierUp'),
                    ask_multiplier_down=raw_pct_price_filter.get('askMultiplierDown'),
                    bid_multiplier_up=raw_pct_price_filter.get('bidMultiplierUp'),
                    bid_multiplier_down=raw_pct_price_filter.get('bidMultiplierDown')
                    )
                )
        if raw_lot_filter := [filter for filter in symbol['filters'] if filter['filterType'] == 'LOT_SIZE']:
            raw_lot_filter = raw_lot_filter[0]
            exc_symbol.filters.append(
                LotFilter(
                    minimum_quantity=raw_lot_filter.get('minQty'),
                    maximum_quantity=raw_lot_filter.get('maxQty'),
                    step_size=raw_lot_filter.get('stepSize'),
                    applies_to_market=False
                    )
                )
        if raw_market_lot_filter := [filter for filter in symbol['filters'] if filter['filterType'] == 'MARKET_LOT_SIZE']:
            raw_market_lot_filter = raw_market_lot_filter[0]
            exc_symbol.filters.append(
                LotFilter(
                    minimum_quantity=raw_market_lot_filter.get('minQty'),
                    maximum_quantity=raw_market_lot_filter.get('maxQty'),
                    step_size=raw_market_lot_filter.get('stepSize'),
                    applies_to_market=True
                    )
                )
        if raw_notional_filter := [filter for filter in symbol['filters'] if filter['filterType'] == 'MIN_NOTIONAL']:
            raw_notional_filter = raw_notional_filter[0]
            exc_symbol.filters.append(
                FundFilter(
                    minimum_notional=raw_notional_filter.get('minNotional'),
                    maximum_notional=raw_notional_filter.get('maxNotional'),
                    apply_max_to_market=raw_notional_filter.get('applyMaxToMarket'),
                    apply_min_to_market=raw_notional_filter.get('applyMinToMarket'),
                    )
                )
        return exc_symbol

    def _prep_order(self, order:dict, symbol:ExchangeSymbol):
        order_time = order.get('time') or order.get('workingTime') or order.get('transactTime') or order.get('updateTime')
        return Order(
            oid=order['orderId'],
            client_oid=order['clientOrderId'],
            symbol=symbol,
            market=self,
            type=order['type'].upper(),
            side=order['side'].upper(),
            price=float(order['price']),
            created=datetime.fromtimestamp(int(order_time // 1000)),
            deal_funds=float(order.get('cummulativeQuoteQty', 0)),
            deal_size=float(order.get('origQty', 0)),
            status=order['status'].upper(),
            funds=float(order.get('origQuoteOrderQty', 0)),
        )
    
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
        
