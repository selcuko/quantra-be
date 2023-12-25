import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

import pytz
from kucoin.client import Market, Trade, User

from filters import FundFilter, LotFilter, PriceFilter
from logger import logger
from markets.helper import authentication_required, float_to_precision
from models import ExchangeSymbol, Order, interval_to_minutes


class KucoinMarket:
    name = 'KUCOIN'
    def __init__(self, config={}) -> None:
        self.authenticated = bool(config.get('API_KEY') and config.get('API_SECRET') and config.get('API_PASSPHRASE'))
        self.testnet = False # KuCoin does not offer a TestNet at the moment (2023-09-22)
        self.spot_trading_enabled = False
        self.capital = 0
        self.assets = {}
        self.commission = {}
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
                self.user = User(
                    key=config['API_KEY'], 
                    secret=config['API_SECRET'], 
                    passphrase=config['API_PASSPHRASE'])
            else:
                self.market = Market()
                self.trade = None
                self.user = None
        except Exception as e:
            logger.fatal(f'Error while initializing {self.name}', exc_info=True)
            raise
        self.symbols = self.get_symbols()
        if self.authenticated:
            self.get_account()
    
    def __str__(self) -> str:
        return f'{self.name} (Authenticated: {self.authenticated})'
    
    def json(self) -> dict:
        return {
            'name': self.name,
            'authenticated': self.authenticated,
            'testnet': self.testnet,
            'spot_trading_enabled': self.spot_trading_enabled,
        }
    
    def _standardize_klines(self, klines:list) -> list[list]:
        try:
            klines.reverse()
            return [[ self._standardize_datetime(kline[0]),
                        float(kline[1]),
                        float(kline[2]),
                        float(kline[3]),
                        float(kline[4]),
                        float(kline[5]),
                    ] for kline in klines ]
        except:
            logger.error(f'Error while standardizing klines for {self.name}: {klines}', exc_info=True)
            raise
    
    def _standardize_symbol(self, symbol:str) -> str:
        return symbol
    
    def _standardize_datetime(self, dt:int) -> datetime:
        return datetime.fromtimestamp(int(dt), tz=pytz.UTC)

    def _format_symbol(self, symbol:str) -> str:
        return symbol.upper()
    
    def _format_interval(self, interval:str) -> str:
        return interval.replace(' ', '')
    
    def _format_datetime(self, dt:datetime) -> int:
        assert isinstance(dt, datetime), f'Expected datetime, got {type(dt)}'
        return int(dt.timestamp())
    
    def _get_symbol_from_name(self, symbol_name:str):
        try:
            return self.symbols[symbol_name]
        except KeyError:
            logger.error(f'Symbol {symbol_name} is not present in {self.name}')
            raise ValueError(f'Symbol {symbol_name} is not present in {self.name}')

    def _prep_symbol(self, symbol:dict) -> ExchangeSymbol:
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
        exc_symbol.filters = {
            'price': [price_filter], 
            'lot': [lot_filter], 
            'fund': [fund_filter]
        }
        return exc_symbol

    def _prep_order_values(self, symbol:ExchangeSymbol, **kwargs) -> float:
        if price := kwargs.get('price'):
            for price_filter in symbol.filters['price']:
                price = price_filter.round(price)
            return price
        if quantity := kwargs.get('quantity'):
            for lot_filter in symbol.filters['lot']:
                quantity = lot_filter.round(quantity)
            return quantity
        if funds := kwargs.get('funds'):
            for fund_filter in symbol.filters['fund']:
                funds = fund_filter.round(funds)
            return funds
        raise ValueError(f'Could not round values for {symbol} with kwargs {kwargs}')

    def _prep_order(self, order:dict, symbol:ExchangeSymbol) -> Order:
        oid = order.get('orderId') or order.get('id')
        return Order(
            oid=oid,
            symbol=symbol,
            market=self,
            type=order.get('type', '').upper(),
            side=order.get('side', '').upper(),
            price=float(order.get('price', 0)),
            created=self._standardize_datetime(order.get('createdAt')) if order.get('createdAt') else None,
            deal_funds=float(order.get('dealFunds', 0)),
            deal_size=float(order.get('dealSize', 0)),
            status='ACTIVE' if order.get('isActive') else 'CLOSED',
            funds=float(order.get('funds', 0)),
            client_oid=order.get('clientOid'),
        )
    def get_earliest__valid_timestamp(self, symbol:str, interval:str, start:datetime) -> datetime:

        klines = self._get_klines(
            symbol=symbol,
            interval=interval,
            start=start,
            end=start + timedelta(minutes=1440),
            limit=1)
        if klines == []:
            return None
        return klines
    def _get_klines(self, symbol:str, interval:str, start:datetime, end:datetime=None, limit=1000, retry=0) -> list[list]:
        if end:
            calculated_end = end
        else:
            calculated_end = start + timedelta(minutes=interval_to_minutes(interval) * limit)
        try:
            klines = self.market.get_kline(
                symbol=self._format_symbol(symbol),
                kline_type=self._format_interval(interval),
                startAt=self._format_datetime(start),
                endAt=self._format_datetime(calculated_end),
                limit=limit)
        except:
            logger.error(f'Error fetching klines for {self._format_symbol(symbol)} from {self.name}', exc_info=True)
            if retry > 0:
                logger.warning(f'Retrying {retry} more times')
                time.sleep(1)
                return self._get_klines(symbol, interval, start, end, limit, retry-1)
            raise
        if not klines or not isinstance(klines, list) or not isinstance(klines[0], list):
            return []
        return self._standardize_klines(klines)

    def get_klines(self, symbol:str, interval:str, start:datetime=None, end:datetime=None, limit=1000, retry=0) -> list[list]:
        if not symbol in self.symbols:
            raise ValueError(f'Symbol {symbol} is not present on {self.name}')
        return self._get_klines(symbol, interval, start, end, limit, retry)
 
    def get_last_klines(self, symbol:str, interval:str, limit=100, retry=1, silent=True) -> list[list]:
        minutes = interval_to_minutes(interval)
        now = datetime.now(tz=pytz.UTC)
        start = now - timedelta(minutes=minutes*limit)
        klines = self.get_klines(symbol, interval, start, now, limit=limit*2)
        if klines == []:
            logger.warning(f'No klines found for {symbol} at {start} -> {now}')
            return []
        last_kline_dt = klines[-1][0]
        if (now - last_kline_dt) > timedelta(minutes=minutes*2):
            error = f'Last kline dt {last_kline_dt} does not match current time {now}, total klines: {len(klines)}, {start} -> {now}'
            logger.warning(error)
            if retry > 0:
                return self.get_last_klines(symbol, interval, limit, retry-1)
            if not silent:
                raise ValueError(error)
        return klines
    
    def get_symbols(self) -> dict[str, ExchangeSymbol]:
        return { self._standardize_symbol(symbol['symbol']): self._prep_symbol(symbol) for symbol in self.market.get_symbol_list_v2()}
    
    @authentication_required
    def place_market_order(self, symbol:ExchangeSymbol|str, side:Literal['buy', 'sell'], funds:float=None, quantity:float=None, validate=True) -> Order:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        client_oid = uuid.uuid4().hex
        if (not funds and not quantity) or (funds and quantity):
            raise ValueError(f'You must provide either funds or quantity to place a market order on {self.name}')
        if funds:
            funds = float_to_precision(Decimal(funds), Decimal(symbol.quote_precision))
        if quantity:
            quantity = float_to_precision(quantity, symbol.base_precision)
        try:
            order = self.trade.create_market_order(
                symbol=symbol.name,
                side=side,
                funds=funds,
                size=quantity,
                client_oid=client_oid)
            logger.info(f'Market order placed on {self.name} for {symbol} with side {side} and funds {funds} and quantity {quantity} with order id {order["orderId"]}')
            order = self._prep_order(order, symbol)
            if validate:
                order = self.get_order(symbol, order.oid)
            return order
        except:
            logger.error(f'Error while placing market order on {self.name}', exc_info=True)
            raise

    @authentication_required
    def place_limit_order(self, symbol:ExchangeSymbol|str, side:Literal['buy', 'sell'], price:float, quantity:float, validate=True) -> Order:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        client_oid = uuid.uuid4().hex
        price = float_to_precision(Decimal(price), Decimal(symbol.quote_precision))
        quantity = float_to_precision(Decimal(quantity), Decimal(symbol.base_precision))
        try:
            order = self.trade.create_limit_order(
                symbol=symbol.name,
                side=side,
                price=self._round_price(symbol, price),
                size=quantity,
                client_oid=client_oid,
            )
            logger.info(f'Limit order placed on {self.name} for {symbol} with side {side} and price {price} and size {quantity} with order id {order["orderId"]}')
            order = self._prep_order(order, symbol)
            if validate:
                order = self.get_order(symbol, order.oid)
            return order
        except:
            logger.error(f'Error while placing limit order on {self.name}', exc_info=True)
            raise

    @authentication_required
    def get_order(self, symbol:ExchangeSymbol|str, order:Order|int) -> Order:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        if isinstance(order, Order):
            order = order.oid
        try:
            order = self.trade.get_order_details(orderId=order)
            return self._prep_order(order, symbol)
        except:
            logger.error(f'Error while getting order {order} on {self.name}', exc_info=True)
            raise
    
    @authentication_required
    def get_orders(self, symbol=ExchangeSymbol|str) -> list[Order]:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        try:
            orders = self.trade.get_order_list(symbol=symbol.name)
            return [self._prep_order(order, symbol) for order in orders['items']]
        except:
            logger.error(f'Error while getting orders on {self.name}', exc_info=True)
            raise
    
    @authentication_required
    def get_open_orders(self, symbol:ExchangeSymbol|str=None) -> list[Order]:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        try:
            if symbol:
                orders = self.trade.get_order_list(symbol=symbol.name, status='active')
            else:
                orders = self.trade.get_order_list(status='active')
            return [self._prep_order(order, symbol) for order in orders['items']]
        except:
            logger.error(f'Error while getting open orders on {self.name}', exc_info=True)
            raise

    @authentication_required
    def cancel_order(self, symbol:ExchangeSymbol|str, order:Order|int) -> Order:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        if isinstance(order, Order):
            order = order.oid
        try:
            order = self.trade.cancel_order(orderOid=order)
            return self._prep_order(order, symbol)
        except:
            logger.error(f'Error while cancelling order {order} on {self.name}', exc_info=True)
            raise
    
    @authentication_required
    def cancel_all_orders(self, symbol:ExchangeSymbol|str=None) -> list[Order]:
        if isinstance(symbol, str):
            symbol = self._get_symbol_from_name(symbol)
        try:
            if symbol:
                orders = self.trade.cancel_all_orders(symbol=symbol.name)
            else:
                orders = self.trade.cancel_all_orders()
            return [self._prep_order(order, symbol) for order in orders['cancelledOrderIds']]
        except:
            logger.error(f'Error while cancelling all orders on {self.name}', exc_info=True)
            raise
    
    @authentication_required
    def get_account(self):
        account = self.user.get_account_list(account_type='trade')
        self.spot_trading_enabled = len(account) > 0
        self.assets = { str(asset['currency']): float(asset['available']) for asset in account }
        self.capital = self.assets.get('USDT', 0)
        fees = self.user.get_base_fee()
        self.commission = {
            'maker': float(fees['makerFeeRate']),
            'taker': float(fees['takerFeeRate']),
            'buyer': float(fees['takerFeeRate']),  # market orders count as taker
            'seller': float(fees['takerFeeRate']), # market orders count as taker
        }

        if not self.spot_trading_enabled:
            logger.error(f'No assets found for account, spot trading disabled on {self.name}')
        if not self.capital:
            logger.error(f'No capital (USDT) found for account on {self.name}')

