from datetime import datetime, timedelta
import time
from typing import Literal
import uuid
from kucoin.client import Market, Trade
from filters import FundFilter, LotFilter, PriceFilter
from logger import logger
from models import ExchangeSymbol, Order, interval_to_minutes
from markets.helper import authentication_required

class KucoinMarket:
    name = 'KUCOIN'
    def __init__(self, config={}) -> None:
        self.authenticated = False
        if config:
            self.authenticated = bool(config.get('API_KEY') and config.get('API_SECRET') and config.get('API_PASSPHRASE'))
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
    
    def __str__(self) -> str:
        return f'{self.name} (Authenticated: {self.authenticated})'
    
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
        return symbol.upper()
    
    def _format_interval(self, interval):
        return interval.replace(' ', '')
    
    def _format_datetime(self, dt):
        return int(dt.timestamp())
    
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
        price, quantity, funds = self._round(symbol, funds=funds, quantity=quantity)
        if error := self._validate_market_order(symbol, funds, quantity):
            raise ValueError(error)
        try:
            logger.info(f'Placing market order on {self.name} for {symbol} with side {side} and funds {funds} and quantity {quantity}')
            order = self.trade.create_market_order(
                symbol=symbol.name,
                side=side,
                funds=funds,
                size=quantity,
                client_oid=client_oid
            )
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
        price, quantity, funds = self._round(symbol, price=price, quantity=quantity)
        if error := self._validate_limit_order(symbol, side, price, quantity):
            raise ValueError(error)
        try:
            logger.info(f'Placing limit order on {self.name} for {symbol} with side {side} and price {price} and size {quantity}')
            order = self.trade.create_limit_order(
                symbol=symbol.name,
                side=side,
                price=self._round_price(symbol, price),
                size=quantity,
                client_oid=client_oid,
            )
            logger.info(f'Limit order placed on {self.name} for {symbol} with side {side} and price {price} and size {quantity} with order id {order["orderId"]}')
            return self._prep_order(order, symbol)
        except:
            logger.error(f'Error while placing limit order on {self.name}', exc_info=True)
            raise

    @authentication_required
    def get_order(self, symbol:ExchangeSymbol, order_id:int) -> Order:
        if isinstance(order_id, Order):
            order_id = order_id.oid
        if not order_id:
            raise ValueError(f'You must provide an order id to get an order on {self.name}')
        try:
            logger.info(f'Getting order {order_id} on {self.name} for {symbol}')
            order = self.trade.get_order_details(orderId=order_id)
            return self._prep_order(order, symbol)
        except:
            logger.error(f'Error while getting order {order_id} on {self.name}', exc_info=True)
            raise
    
    @authentication_required
    def get_orders(self, symbol=ExchangeSymbol) -> list[Order]:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        try:
            logger.info(f'Getting orders on {self.name} for {symbol}')
            orders = self.trade.get_order_list(symbol=symbol.name)
            return [self._prep_order(order, symbol) for order in orders['items']]
        except:
            logger.error(f'Error while getting orders on {self.name}', exc_info=True)
            raise
    
    @authentication_required
    def get_open_orders(self, symbol:ExchangeSymbol=None) -> list[Order]:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        try:
            logger.info(f'Getting open orders on {self.name} for {symbol}')
            orders = self.trade.get_order_list(symbol=symbol, status='active')
            return [self._prep_order(order, symbol) for order in orders['items']]
        except:
            logger.error(f'Error while getting open orders on {self.name}', exc_info=True)
            raise

    @authentication_required
    def cancel_order(self, symbol:ExchangeSymbol, order_id:int) -> Order:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        try:
            logger.info(f'Cancelling order {order_id} on {self.name}')
            order = self.trade.cancel_order(orderOid=order_id)
            return self._prep_order(order, symbol)
        except:
            logger.error(f'Error while cancelling order {order_id} on {self.name}', exc_info=True)
            raise
    
    @authentication_required
    def cancel_all_orders(self, symbol:ExchangeSymbol=None) -> list[Order]:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        try:
            if symbol:
                logger.info(f'Cancelling all orders on {self.name} for {symbol}')
                orders = self.trade.cancel_all_orders(symbol=symbol.name)
            else:
                logger.info(f'Cancelling all orders on {self.name}')
                orders = self.trade.cancel_all_orders()
            return [self._prep_order(order, symbol) for order in orders['cancelledOrderIds']]
        except:
            logger.error(f'Error while cancelling all orders on {self.name}', exc_info=True)
            raise

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
            logger.debug(f'Hitting Kucoin API for {self._format_symbol(symbol)} at {start} -> {end} with limit {limit}')
            klines = self.market.get_kline(
                symbol=self._format_symbol(symbol),
                kline_type=self._format_interval(interval),
                startAt=self._format_datetime(start),
                endAt=self._format_datetime(end),
                limit=limit
            )
        except:
            logger.error(f'Error while fetching klines for {self._format_symbol(symbol)} from {self.name}', exc_info=True)
            if retry > 0:
                logger.warning(f'Retrying {retry} more times')
                time.sleep(1)
                return self._get_klines(symbol, interval, start, end, limit, retry-1)
            raise
        if not klines or not isinstance(klines, list) or not isinstance(klines[0], list):
            return []
        return self._standardize_klines(klines)

    def get_symbols(self):
        return { self._standardize_symbol(symbol['symbol']): self._prep_symbol(symbol) for symbol in self.market.get_symbol_list_v2()}
    
    def _prep_symbol(self, symbol:dict):
        exc_symbol = ExchangeSymbol(
            name = symbol['symbol'],
            base = symbol['baseCurrency'],
            quote = symbol['quoteCurrency'],
            base_precision = symbol['baseIncrement'],
            quote_precision = symbol['quoteIncrement'],
            spot_trading_enabled = symbol['enableTrading'],
            margin_trading_enabled = symbol['isMarginEnabled'],
        )
        price_filter = PriceFilter(
            ask_multiplier_down = symbol['priceLimitRate'],
            ask_multiplier_up = symbol['priceLimitRate'],
            bid_multiplier_down = symbol['priceLimitRate'],
            bid_multiplier_up = symbol['priceLimitRate'],
            tick_size = symbol['priceIncrement'],
        )
        lot_filter = LotFilter(
            minimum_quantity = symbol['baseMinSize'],
            maximum_quantity = symbol['baseMaxSize'],
            step_size = symbol['baseIncrement'],
        )
        fund_filter = FundFilter(
            minimum_notional = symbol['minFunds'],
            maximum_notional = symbol['quoteMaxSize'],
        )
        exc_symbol.filters = {'price': price_filter, 'lot': lot_filter, 'fund': fund_filter}
        return exc_symbol

    def _prep_order(self, order:dict, symbol:ExchangeSymbol):
        oid = order.get('orderId') or order.get('id')
        return Order(
            oid=oid,
            symbol=symbol,
            market=self,
            type=order.get('type', '').upper(),
            side=order.get('side', '').upper(),
            price=float(order.get('price', 0)),
            created=datetime.fromtimestamp(int(order.get('createdAt'))/1000) if order.get('createdAt') else None,
            deal_funds=float(order.get('dealFunds', 0)),
            deal_size=float(order.get('dealSize', 0)),
            status='ACTIVE' if order.get('isActive') else 'CLOSED',
            funds=float(order.get('funds', 0)),
            client_oid=order.get('clientOid'),
        )
    
    def _round(self, symbol, price=None, quantity=None, funds=None):
        if price and (price_filter := symbol.filters.get('price')):
            price = price_filter.round(price)
        if quantity and (lot_filter := symbol.filters.get('lot')):
            quantity = lot_filter.round(quantity)
        if funds and (fund_filter := symbol.filters.get('fund')):
            funds = fund_filter.round(funds)
        return price, quantity, funds

    def _validate_market_order(self, symbol, funds, quantity):
        if lot_filter := symbol.filters.get('lot'):
            if quantity:
                try:
                    lot_filter.validate(quantity, 'market')
                except ValueError as e:
                    return str(e)
        if fund_filter := symbol.filters.get('fund'):
            if funds:
                try:
                    fund_filter.validate(funds, 'market')
                except ValueError as e:
                    return str(e)
    
    def _validate_limit_order(self, symbol, side, price, quantity):
        if price_filter := symbol.filters.get('price'):
            try:
                price_filter.validate(price, side)
            except ValueError as e:
                return str(e)
        if lot_filter := symbol.filters.get('lot'):
            try:
                lot_filter.validate(quantity, 'limit')
            except ValueError as e:
                return str(e)
    
    def get_last_klines(self, symbol, interval, limit=100):
        minutes = interval_to_minutes(interval)
        now = datetime.now()
        start = now - timedelta(minutes=minutes*limit)
        klines = self.get_klines(symbol, interval, start, now)
        last_kline_dt = klines[-1][0]
        if (now - last_kline_dt) > timedelta(minutes=minutes*2):
            error = f'Last kline dt {last_kline_dt} does not match current time {now}, total klines: {len(klines)}, {start} -> {now}'
            logger.warning(error)
            raise Exception(error)
        return klines