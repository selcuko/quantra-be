from datetime import datetime, timedelta
import json
import os
from tabnanny import verbose
import threading
import typing
from django.conf import settings
from django.contrib.auth.models import User
from logger import logger
import pytz
from typing import Optional
from django.db import models
from cryptography.fernet import Fernet
from markets import get_market
from markets.helper import float_to_precision

from strategy import get_strategy
from decimal import Decimal
if typing.TYPE_CHECKING:
    from liveloop import LiveLoop


class Market(models.Model):
    class Exchange(models.TextChoices):
        BINANCE = 'BINANCE', 'Binance'
        BYBIT = 'BYBIT', 'Bybit'
        GATEIO = 'GATEIO', 'Gate.io'
        OKX = 'OKX', 'OKX'
        KUCOIN = 'KUCOIN', 'KuCoin'
        MEXC = 'MEXC', 'MEXC'
    exchange_name = models.CharField(max_length=30, choices=Exchange.choices, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    symbols: models.QuerySet['MarketSymbol']
    prices = models.TextField(null=True, blank=True, help_text='Prices of symbols in this market')
    prices_updated = models.DateTimeField(null=True, blank=True, help_text='Last time prices were updated')

    def filters(self, symbol):
        details = json.loads(symbol.details or '{}', )
        if self.exchange_name == Market.Exchange.BINANCE:
            filters = {f['filterType']: f for f in details.get('filters', [])}
            lot_step = filters.get('LOT_SIZE', {}).get('stepSize')
            price_size = filters.get('PRICE_FILTER', {}).get('tickSize')
            return {
                'min_notional': Decimal(filters.get('MIN_NOTIONAL', {}).get('minNotional')) if filters.get('MIN_NOTIONAL', {}).get('applyToMarket') else None,
                'lot_step': Decimal(lot_step) if lot_step else None,
                'price_step': Decimal(price_size) if price_size else None,
            }
        elif self.exchange_name == Market.Exchange.KUCOIN:
            return {
                'min_notional': Decimal(details.get('minFunds')) if details.get('minFunds') else None,
                'lot_step': Decimal(details.get('baseIncrement')) if details.get('baseIncrement') else None,
                'price_step': Decimal(details.get('priceIncrement')) if details.get('priceIncrement') else None,
            }
        elif self.exchange_name == Market.Exchange.MEXC:
            return {
                'price_step': Decimal(details.get('quoteAmountPrecision')) if details.get('quoteAmountPrecision') else None,
                'lot_step': Decimal(details.get('baseSizePrecision')) if details.get('baseSizePrecision') else None,
                'min_notional': Decimal(details.get('minQuoteAmountMarket')) if details.get('minQuoteAmountMarket') else None,
            }
        elif self.exchange_name == Market.Exchange.BYBIT:
            price_tick = details.get('priceFilter', {}).get('tickSize')
            lot_size = details.get('lotSizeFilter', {}).get('basePrecision')
            notional = details.get('lotSizeFilter', {}).get('minOrderQty')
            return {
                'min_notional': Decimal(notional) if notional else None,
                'lot_step': Decimal(lot_size) if lot_size else None,
                'price_step': Decimal(price_tick) if price_tick else None,
            }
        else:
            return {
                'min_notional': None,
                'lot_step': None,
                'price_step': None,
            }

    def __str__(self):
        return self.exchange_name


def three_months_later():
    return datetime.now(pytz.utc) + timedelta(days=90)

class MarketCredentials(models.Model):
    market     = models.ForeignKey(Market, on_delete=models.PROTECT, related_name='credentials')
    encrypted  = models.TextField(help_text='Encrypted credentials. This field is encrypted automatically if it contains valid JSON data.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(default=three_months_later)
    owner      = models.CharField(max_length=30)
    internal   = models.BooleanField(default=False, help_text='Owned by a team member')
    active     = models.BooleanField(default=True, help_text='Account can be used for trading')

    class Meta:
        verbose_name_plural = 'Market credentials'

    def __str__(self) -> str:
        return f'{self.market} {self.owner}'

    def save(self, *args, **kwargs):
        if self.encrypted:
            try:
                data = json.loads(self.encrypted)
                fernet = Fernet(settings.SYMKEY)
                self.encrypted = fernet.encrypt(data.dumps().encode()).decode()
            except:
                pass
        create_market_account = not bool(self.pk)
        super().save(*args, **kwargs)
        if create_market_account:
            MarketAccount.objects.create(market=self.market, credentials=self)

    @property
    def decrypted(self) -> dict[str, str]:
        try:
            fernet = Fernet(settings.SYMKEY)
            return json.loads(fernet.decrypt(self.encrypted.encode()).decode())
        except:
            logger.error(f'Could not decrypt credentials for {self.market.exchange_name}', exc_info=True)
            return {}


class MarketAccount(models.Model):
    market      = models.ForeignKey(Market, on_delete=models.PROTECT, related_name='accounts')
    credentials = models.ForeignKey(MarketCredentials, on_delete=models.PROTECT, related_name='accounts')
    equity     = models.FloatField(null=True, blank=True, help_text='Total USDT equity in this account')
    capital    = models.FloatField(null=True, blank=True, help_text='Total USDT capital in this account')
    assets     = models.TextField(null=True, blank=True, help_text='Assets in this account')
    last_cache = models.DateTimeField(null=True, blank=True, help_text='Last time equity/assets were updated')

    def __str__(self):
        return f'{self.market.exchange_name} {self.credentials.owner} (${self.equity or 0})'

    def save(self, *args, **kwargs):
        if self.market != self.credentials.market:
            raise ValueError('Market and credentials should be for the same market.')
        super().save(*args, **kwargs)
    
    def get_interface(self):
        from markets import get_market
        return get_market(self.market.exchange_name, self.credentials.decrypted, self)

    @property
    def available_capital(self):
        assets = json.loads(self.assets or '{}')
        if not self.capital:
            return None
        return self.capital

    @property
    def owner(self):
        return self.credentials.owner
    
    @property
    def active(self):
        return self.credentials.active
    
    @property
    def internal(self):
        return self.credentials.internal
    
    @property
    def exchange(self):
        return self.market.exchange_name
    
    @classmethod
    def get_available_accounts(cls, only_internal=False):
        if only_internal:
            return cls.objects.filter(credentials__internal=True, credentials__active=True)
        return cls.objects.filter(credentials__active=True)

class MarketSymbol(models.Model):
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name', 'market'], name='unique_symbol')
        ]
    symbol = models.ForeignKey('GlobalSymbol', on_delete=models.PROTECT, related_name='symbols', null=True, blank=True)
    market = models.ForeignKey(Market, on_delete=models.PROTECT, related_name='symbols')
    base = models.CharField(max_length=30)
    quote = models.CharField(max_length=30)
    name = models.CharField(max_length=60)
    base_precision = models.DecimalField(null=True, blank=True, max_digits=20, decimal_places=10, help_text='Number of decimal places for base currency')
    quote_precision = models.DecimalField(null=True, blank=True, max_digits=20, decimal_places=10, help_text='Number of decimal places for quote currency')
    spot_trading_enabled = models.BooleanField(default=True, help_text='Spot trading enabled for this symbol in related market')
    margin_trading_enabled = models.BooleanField(default=False, help_text='Margin trading enabled for this symbol in related market')
    details = models.TextField(null=True, blank=True, help_text='JSON string of symbol detail from market')
    sessions: models.QuerySet['Session']

    hour4_volume = models.FloatField(null=True, blank=True, help_text='Volume in the last 4 hours')
    hour4_volume_date = models.DateTimeField(null=True, blank=True, help_text='Start date of the candle used for last 4 hour volume')
    day10_volume = models.FloatField(null=True, blank=True, help_text='Volume in the last 10 days')
    day10_volume_date = models.DateTimeField(null=True, blank=True, help_text='Start date of the candle used for last 10 day volume')
    day30_volume = models.FloatField(null=True, blank=True, help_text='Volume in the last 30 days')
    day30_volume_date = models.DateTimeField(null=True, blank=True, help_text='Start date of the candle used for last 30 day volume')
    day60_volume = models.FloatField(null=True, blank=True, help_text='Volume in the last 60 days')
    day60_volume_date = models.DateTimeField(null=True, blank=True, help_text='Start date of the candle used for last 60 day volume')

    def save(self, *args, **kwargs):
        if not self.name and self.base and self.quote:
            self.name = f'{self.base}-{self.quote}'
        if not self.base and not self.quote and self.name:
            self.base, self.quote = self.name.split('-')
        super().save(*args, **kwargs)

    def to_dict(self):
        return {
            'name': self.name,
            'base': self.base,
            'quote': self.quote,
            'base_precision': self.base_precision,
            'quote_precision': self.quote_precision,
            'spot_trading_enabled': self.spot_trading_enabled,
        }

    def __str__(self):
        try:
            return f'{self.name}@{self.market.exchange_name}'
        except:
            return f'{self.name}@NOMARKET'

    def filters(self):
        return self.market.filters(self)



class Session(models.Model):
    class CandleSource(models.TextChoices):
        TRADE = 'TRADE', 'Trade'
        WEBSOCKET = 'WEBSOCKET', 'Websocket'
        REST  = 'REST',  'REST'
    class Type(models.TextChoices):
        BACKTEST     = 'backtest',     'Backtest'
        LIVE_BASIC   = 'live.basic',   'Live Basic'
        LIVE_SANDBOX = 'live.sandbox', 'Live Testnet'
        LIVE_MAINNET = 'live.mainnet', 'Live Mainnet'
    class Status(models.TextChoices):
        ONGOING    = 'ONGOING',    'Ongoing'
        COMPLETED  = 'COMPLETED',  'Completed'
        ERROR      = 'ERROR',      'Error'
        PURGED     = 'PURGED',     'Purged'
        PAUSED     = 'PAUSED',     'Paused'
        PLANNED    = 'PLANNED',    'Planned'
        TERMINATED = 'TERMINATED', 'Terminated'
    class Freq(models.TextChoices):
        MIN1  = '1 min',  '1 minute'
        MIN3  = '3 min',  '3 minutes'
        MIN5  = '5 min',  '5 minutes'
        MIN15 = '15 min', '15 minutes'
        MIN30 = '30 min', '30 minutes'
        HOUR1 = '1 hour', '1 hour'
        HOUR2 = '2 hour', '2 hours'
        HOUR4 = '4 hour', '4 hours'
        HOUR6 = '6 hour', '6 hours'
        HOUR8 = '8 hour', '8 hours'
        HOUR12 = '12 hour', '12 hours'
        DAY1  = '1 day',  '1 day'

    session_type = models.CharField(max_length=30, choices=Type.choices)
    freq = models.CharField(max_length=30)
    account = models.ForeignKey(MarketAccount, on_delete=models.PROTECT, related_name='sessions')
    group = models.ForeignKey('SessionGroup', on_delete=models.PROTECT, related_name='sessions', null=True, blank=True)
    started = models.DateTimeField(auto_now_add=True)
    ended = models.DateTimeField(null=True, blank=True)
    symbol = models.ForeignKey(MarketSymbol, on_delete=models.PROTECT, related_name='sessions')
    strategy = models.ForeignKey('Strategy', on_delete=models.PROTECT, related_name='sessions', null=True, blank=True)
    planned_shutdown = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=Status.choices)
    report = models.CharField(max_length=256, null=True, blank=True, help_text='Report file name')
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    last_price = models.FloatField(null=True, blank=True)
    last_kline_timestamp = models.DateTimeField(null=True, blank=True)
    signals: models.QuerySet['Signal']
    subscriptions: models.QuerySet['Subscription']
    initial_capital = models.FloatField()
    initial_assets = models.FloatField()
    capital = models.FloatField()
    assets = models.FloatField()
    thread_id = models.BigIntegerField(null=True, blank=True)
    use_heikin_ashi = models.BooleanField(default=False)
    candle_source = models.CharField(max_length=30, choices=CandleSource.choices, default=CandleSource.TRADE)
    strategy_parameters = models.TextField(null=True, blank=True, help_text='JSON string of parameters for this strategy, leave blank to use defaults.')
    details = models.TextField(null=True, blank=True, help_text='JSON string of session details from market')
    initial_price = models.FloatField(null=True, blank=True)
    buy_enabled = models.BooleanField(default=True)
    sell_enabled = models.BooleanField(default=True)
    initiated_at = models.DateTimeField(auto_now_add=True)
    orders: models.QuerySet['Order']

    @property
    def equity(self):
        return self.capital + (self.assets * self.last_price if self.last_price else 0)

    def save(self, *args, **kwargs):
        if not self.account:
            raise ValueError('Session must have at least an account before saving.')
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.strategy} - {self.symbol} - {self.status}'
    
    @property
    def analytics(self):
        from quantapi.analytics import SessionAnalytics
        return SessionAnalytics(self)

    @property
    def thread(self):
        threads = threading.enumerate()
        for thread in threads:
            if thread.ident == self.thread_id and thread.is_alive():
                return thread

    def resume(self):
        """Resume an interrupted session."""
        if self.group:
            raise ValueError('Cannot resume a session that belongs to a group, try resuming the SessionGroup instead')
        if not self.status == Session.Status.ONGOING:
            raise ValueError(f'Session status should be ONGOING to resume, not {self.status}')
        if not self.pk:
            raise ValueError('Session must be saved before resuming')
        if not self.strategy:
            raise ValueError('Session must have a strategy to resume')
        from liveloop import LiveLoop
        strategy = get_strategy(self.strategy.name)
        ll = LiveLoop(
            symbol=self.symbol.name,
            account=self.account,
            strategy=strategy(params=json.loads(self.strategy_parameters or '{}')),
            capital_limit=self.capital,
            asset_limit=self.assets,
            freq=self.freq,
            end=self.planned_shutdown,
            session=self)
        if self.candle_source == Session.CandleSource.WEBSOCKET:
            ll.run(websocket=True)
        elif self.candle_source == Session.CandleSource.REST:
            ll.run(polling=True)
        elif self.candle_source == Session.CandleSource.TRADE:
            ll.run(match_engine=True)
        else:
            raise ValueError(f'Invalid candle source: {self.candle_source}')
        return ll

    def stop(self):
        """Stop an ongoing session."""
        if self.status == Session.Status.ONGOING:
            self.status = Session.Status.COMPLETED
            self.planned_shutdown = datetime.now(pytz.utc)
        else:
            raise ValueError(f'Session status should be ONGOING to stop, not {self.status}')

    def recent_order_error(self):
        # return True if if there is an order with status ERROR in the last 5 orders
        orders = Order.objects.filter(signal__session=self).order_by('-created_at')[:5]
        orders = orders.filter(status=Order.Status.ERROR)
        return orders.exists()

    def update(self, interface, save=True):
        interface = interface or self.account.get_interface()
        new_capital = min(self.capital, interface.capital)
        new_assets  = min(self.assets, interface.assets.get(self.symbol.base, 0))
        if new_capital != self.capital:
            logger.warning(f'Capital changed from {self.capital} to {new_capital} (SessionID:{self.pk})')
        if new_assets != self.assets:
            logger.warning(f'Assets changed from {self.assets} to {new_assets} (SessionID:{self.pk})')
        self.capital = new_capital
        self.assets = new_assets
        if save: self.save()


class SessionGroup(models.Model):
    class Status(models.TextChoices):
        PLANNED = 'PLANNED', 'Planned'
        ONGOING = 'ONGOING', 'Ongoing'
        COMPLETED = 'COMPLETED', 'Completed'
        ERROR = 'ERROR', 'Error'
        PAUSED = 'PAUSED', 'Paused'
        PURGED = 'PURGED', 'Purged'

    symbol = models.ForeignKey(MarketSymbol, on_delete=models.PROTECT, related_name='groups')
    market = models.ForeignKey(Market, on_delete=models.PROTECT, related_name='groups')
    sessions: models.QuerySet['Session']
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    strategy = models.ForeignKey('Strategy', on_delete=models.PROTECT, related_name='groups')
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PLANNED)
    last_kline_dt = models.DateTimeField(null=True, blank=True, verbose_name='Last candle timestamp')
    last_price = models.FloatField(null=True, blank=True, verbose_name='Last price')
    thread_id = models.BigIntegerField(null=True, blank=True, verbose_name='Thread ID')
    buy_enabled = models.BooleanField(default=True)
    sell_enabled = models.BooleanField(default=True)
    source = models.CharField(max_length=30, choices=Session.CandleSource.choices, default=Session.CandleSource.TRADE)
    freq = models.CharField(max_length=30, choices=Session.Freq.choices, default=Session.Freq.MIN15)

    def save(self, *args, **kwargs):
        if self.pk:
            sessions = self.sessions.all()
            for session in sessions:
                if session.symbol != self.symbol or (session.strategy and session.strategy != self.strategy):
                    print(self.symbol, session.symbol, self.strategy, session.strategy)
                    raise ValueError('All sessions in a group should have the same symbol and strategy.')
        super().save(*args, **kwargs)

    @property
    def capital(self):
        return sum([session.capital for session in self.sessions.all()])

    @property
    def assets(self):
        return sum([session.assets for session in self.sessions.all()])

    @property
    def equity(self):
        return sum([session.equity for session in self.sessions.all()])

    @property
    def thread(self):
        threads = threading.enumerate()
        for thread in threads:
            if thread.ident == self.thread_id and thread.is_alive():
                return thread

    def resume(self):
        if not self.status == SessionGroup.Status.ONGOING:
            raise ValueError(f'SessionGroup status should be ONGOING to resume, not {self.status}')
        if not self.pk:
            raise ValueError('SessionGroup must be saved before resuming')
        if not self.strategy:
            raise ValueError('SessionGroup must have a strategy to resume')
        from loopgroup import LoopGroup
        loop = LoopGroup(group=self, freq=self.freq)
        try:
            loop.run(source=self.source)
        except Exception as e:
            raise SessionCannotContinue(f'Failed to resume group {self} due to {e!r}')
        return loop
    
    def add_account(self, account:MarketAccount):
        if not self.pk:
            raise ValueError('SessionGroup must be saved before adding accounts.')
        if account.market != self.market:
            raise ValueError(f'Account should be for the same market as the group (account.market={account.market}, group.market={self.market}).')
        for session in self.sessions.all():
            if session.account == account:
                return
        session = Session.objects.create(
            group=self,
            freq=self.freq,
            account=account,
            symbol=self.symbol,
            strategy=self.strategy,
            status=self.status,
            initial_capital=0,
            initial_assets=0,
            capital=0,
            assets=0,
        )
        return session


class SessionCannotContinue(Exception):
    pass


class Strategy(models.Model):
    name = models.CharField(max_length=30)
    technical_name = models.CharField(max_length=30, null=True, blank=True)
    code = models.CharField(max_length=5, default='null')
    version = models.CharField(max_length=30, default='1.0')
    description = models.CharField(max_length=256, null=True, blank=True)
    sessions: models.QuerySet[Session]

    class Meta:
        verbose_name_plural = 'Strategies'

    def __str__(self):
        return f'{self.name} {self.version}'


class Signal(models.Model):
    class Side(models.TextChoices):
        BUY = 'BUY'
        SELL = 'SELL'
    session = models.ForeignKey(Session, on_delete=models.PROTECT, related_name='signals', null=True, blank=True)
    group = models.ForeignKey(SessionGroup, on_delete=models.PROTECT, related_name='signals', null=True, blank=True)
    timestamp = models.DateTimeField()
    side = models.CharField(max_length=30, choices=Side.choices)
    price = models.FloatField()
    raw = models.CharField(max_length=512)
    orders: models.QuerySet['Order']

    def save(self, *args, **kwargs):
        if not self.group and not self.session:
            raise ValueError('Signal must belong to a Session or a SessionGroup.')
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f'{self.side} {self.symbol} {self.price}'
    
    @property
    def symbol(self):
        return self.session.symbol if self.session else self.group.symbol if self.group else None

    @property
    def cum_order(self):
        orders = self.orders.all()
        all_filled = all([order.status == Order.Status.FILLED for order in orders])
        return Order(
            price=self.price,
            oid='cumulative',
            client_oid='cumulative',
            deal_size=sum([order.deal_size for order in orders if order.deal_size]),
            deal_funds=sum([order.deal_funds for order in orders if order.deal_funds]),
            funds=sum([order.funds for order in orders if order.funds]),
            order_type=Order.Type.MARKET,
            signal=self,
            created_at=self.timestamp,
            status=Order.Status.FILLED if all_filled else Order.Status.OPEN,
            side=self.side,
            symbol=self.symbol,
        )



class Order(models.Model):
    class Type(models.TextChoices):
        MARKET = 'MARKET'
        LIMIT = 'LIMIT'
    class Side(models.TextChoices):
        BUY = 'BUY'
        SELL = 'SELL'
    class Status(models.TextChoices):
        NOT_PLACED = 'NOT_PLACED'
        OPEN = 'OPEN'
        FILLED = 'FILLED'
        CANCELLED = 'CANCELLED'
        REJECTED = 'REJECTED'
        EXPIRED = 'EXPIRED'
        ERROR = 'ERROR'
        INSUFFICIENT_BALANCE = 'INSUFFICIENT_BALANCE'

    oid = models.CharField(max_length=256, unique=True, null=True, blank=True)
    client_oid = models.CharField(max_length=256, unique=True, null=True, blank=True)
    deal_size = models.FloatField(help_text='Amount of quote currency in this order (e.g. BTC)', null=True, blank=True)
    price = models.FloatField(help_text='Price represented as (price of base)/(price of quote)', null=True, blank=True)
    deal_funds = models.FloatField(help_text='Amount of base currency in this order (e.g. USDT)', null=True, blank=True)
    funds = models.FloatField(help_text='Amount of base currency of this order initially placed with', null=True, blank=True)
    order_type = models.CharField(max_length=30, choices=Type.choices, default=Type.MARKET)
    signal = models.ForeignKey(Signal, on_delete=models.PROTECT, related_name='orders', null=True, blank=True)
    market_timestamp = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=Status.choices)
    force = models.BooleanField(default=False)
    details = models.TextField(null=True, blank=True)
    request = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    placed_at = models.DateTimeField(null=True, blank=True)
    side = models.CharField(max_length=30, choices=Side.choices, null=True)
    messages_raw = models.TextField(default='')
    pnl = models.FloatField(null=True, blank=True)
    average_cost = models.FloatField(null=True, blank=True)
    session = models.ForeignKey(Session, on_delete=models.PROTECT, related_name='orders', null=True, blank=True)
    symbol = models.ForeignKey(MarketSymbol, on_delete=models.PROTECT, related_name='orders')
    market = models.ForeignKey(Market, on_delete=models.PROTECT, related_name='orders')

    def save(self, *args, **kwargs):
        if not self.side and self.signal: 
            self.side = self.signal.side
        if not self.price and self.deal_funds and self.deal_size:
            self.price = self.deal_funds / self.deal_size
        if not self.deal_funds and self.price and self.deal_size:
            self.deal_funds = self.price * self.deal_size
        if not self.deal_size and self.price and self.deal_funds:
            self.deal_size = self.deal_funds / self.price
        if not self.funds and self.deal_funds:
            self.funds = self.deal_funds
        super().save(*args, **kwargs)
        if not self.pnl and not self.average_cost:
            from quantapi.analytics import OrderAnalytics
            order_analytics = OrderAnalytics(self)
            self.pnl = order_analytics.pnl
            self.average_cost = order_analytics.average_cost
            if self.pnl or self.average_cost:
                super().save(*args, **kwargs)

    @property
    def messages(self):
        return self.messages_raw.split('\n')
    
    @messages.setter
    def messages(self, value):
        self.messages_raw = '\n'.join(value)

    def add_message(self, message):
        messages = self.messages
        messages.append(message)
        self.messages = messages

    def __str__(self) -> str:
        if self.side == Order.Side.BUY:
            return f'{self.status} {self.order_type.title()} {self.side} Order: ${self.deal_funds} worth of {self.symbol.name}'
        elif self.side == Order.Side.SELL:
            return f'{self.status} {self.order_type.title()} {self.side} Order: {self.deal_size} {self.symbol.base}'
        return f'{self.status} {self.order_type.title()} Order: {self.symbol.name}'

    def refresh_from_market(self, market_interface):
        if not self.oid:
            raise ValueError('Cannot refresh order without oid')
        order = market_interface.get_order(self.symbol, self.oid)
        self.status = order.status
        self.deal_funds = order.deal_funds
        self.price = order.price
        self.deal_size = order.deal_size
        self.funds = order.funds
        self.order_type = order.order_type
        self.market_timestamp = order.market_timestamp
        self.client_oid = order.client_oid
        self.save()

    @property
    def display_price(self):
        if self.price and float(self.price) > 0:
            return self.price
        elif self.deal_funds and self.deal_size:
            return self.deal_funds / self.deal_size
        return None

    def to_dict(self):
        return {
            'id': self.pk,
            'oid': self.oid,
            'client_oid': self.client_oid,
            'deal_size': self.deal_size,
            'price': self.price,
            'deal_funds': self.deal_funds,
            'funds': self.funds,
            'order_type': self.order_type,
            'status': self.status,
            'force': self.force,
            'details': self.details,
            'request': self.request,
            'placed_at': self.placed_at,
            'side': self.side,
            'messages_raw': self.messages_raw,
            'pnl': self.pnl,
            'average_cost': self.average_cost,
            'session': self.session.pk if self.session else None,
            'symbol': self.symbol.name,
            'market': self.market.exchange_name,
        }


class ComplexOrder(models.Model):
    class Type(models.TextChoices):
        TARGET_PRICE = 'TARGET_PRICE'
    class Status(models.TextChoices):
        PENDING = 'PENDING'
        FILLED = 'FILLED'
        ERRORED = 'ERRORED'

    type = models.CharField(max_length=30, choices=Type.choices, default=Type.TARGET_PRICE)
    status = models.CharField(max_length=30, choices=Status.choices)
    session = models.ForeignKey(Session, on_delete=models.PROTECT, related_name='complex_orders')
    target_price = models.FloatField(null=True, blank=True)
    deal_funds = models.FloatField(null=True, blank=True)
    deal_size = models.FloatField(null=True, blank=True)
    side = models.CharField(max_length=30, choices=Order.Side.choices)
    market_order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name='complex_order', null=True, blank=True)

    def __str__(self) -> str:
        return f'{self.status} {self.type} @ {self.session.symbol.base}'

    def is_ready(self, ll:'LiveLoop') -> bool:
        if self.type == ComplexOrder.Type.TARGET_PRICE and self.target_price:
            if self.side == Order.Side.BUY:
                return ll.session.last_price <= self.target_price if ll.session.last_price else False
            elif self.side == Order.Side.SELL:
                return ll.session.last_price >= self.target_price if ll.session.last_price else False
        return False

    def execute(self, ll:'LiveLoop'):
        pass


class Subscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='subscriptions')
    session = models.ForeignKey(Session, on_delete=models.PROTECT, related_name='subscriptions')

    def __str__(self) -> str:
        return f'SUB {self.user.username} - {self.session.strategy} - {self.session.symbol.name}'


class Endpoint(models.Model):
    class Type(models.TextChoices):
        TELEGRAM = 'TELEGRAM'
    class Group(models.TextChoices):
        TRADER = 'TRADER'
        ADMIN = 'ADMIN'
        DEVOPS = 'DEVOPS'
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='endpoints')
    endpoint_type = models.CharField(max_length=30, choices=Type.choices)
    external_id = models.CharField(max_length=256)
    group = models.CharField(max_length=30, choices=Group.choices, default=Group.ADMIN)

    def __str__(self) -> str:
        return f'{self.endpoint_type} {self.external_id}'


class Notification(models.Model):
    class Severity(models.TextChoices):
        INFO = 'INFO'
        WARNING = 'WARNING'
        ERROR = 'ERROR'
        CRITICIAL = 'CRITICAL'
    class Type(models.TextChoices):
        ORDER = 'ORDER'
        SIGNAL = 'SIGNAL'
        EXCEPTION = 'EXCEPTION'
        CRASH = 'CRASH'
        DEBUG = 'DEBUG'
        LOG = 'LOG'

    class State(models.TextChoices):
        NEW = 'NEW'
        SENT = 'SENT'
        SENT_PARTIAL = 'SENT_PARTIAL'
        ERROR = 'ERROR'

    severity = models.CharField(max_length=30, choices=Severity.choices, default=Severity.INFO)
    notification_type = models.CharField(max_length=30, choices=Type.choices, default=Type.DEBUG)
    state = models.CharField(max_length=30, choices=State.choices, default=State.NEW)
    subject = models.CharField(max_length=256, null=True, blank=True)
    message = models.TextField()
    details = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    sent_to = models.ManyToManyField(Endpoint, related_name='notifications', blank=True)
    acknowledged_by = models.ManyToManyField(User, related_name='acknowledged_notifications', blank=True)

    def __str__(self) -> str:
        return f'{self.severity} {self.notification_type} {self.state} {self.subject or ""}'

    def send(self):
        from telegram import send_message
        if not self.pk:
            self.save()
        message = f'[{self.severity}] {self.message}'
        sent_to = []
        already_sent_to = self.sent_to.all()
        for endpoint in Endpoint.objects.all():
            if endpoint in already_sent_to:
                sent_to.append(endpoint)
                continue
            try:
                send_message(int(endpoint.external_id), message)
                sent_to.append(endpoint)
            except:
                logger.error(f'Failed to send notification to {endpoint.external_id} (notification {self.pk})')
        self.sent_to.add(*sent_to)
        if len(sent_to) == 0:
            self.state = Notification.State.ERROR
        elif len(sent_to) < len(Endpoint.objects.all()):
            self.state = Notification.State.SENT_PARTIAL
        else:
            self.state = Notification.State.SENT
        self.save()
    
    def save(self, *args, **kwargs):
        if not self.subject:
            self.subject = f'{self.severity} {self.notification_type} Message (No Subject)'
        super().save(*args, **kwargs)


class Backtest(models.Model):
    class Status(models.TextChoices):
        INIT = 'INIT'
        ONGOING = 'ONGOING'
        ERROR = 'ERROR'
        COMPLETED = 'COMPLETED'
    timestamp = models.DateTimeField(auto_now_add=True)
    start = models.DateTimeField()
    end = models.DateField(null=True, blank=True)
    profit = models.FloatField(null=True, blank=True)
    freq = models.CharField(max_length=100, choices=Session.Freq.choices)
    report = models.TextField(null=True, blank=True)
    symbol = models.CharField(max_length=100)
    market = models.CharField(max_length=100)
    status = models.CharField(max_length=100, choices=Status.choices)
    details = models.TextField(null=True, blank=True)
    use_heikin_ashi = models.BooleanField(default=False)
    parameters = models.TextField(null=True, blank=True)

    def __str__(self) -> str:
        return f'{self.symbol} {self.market} {self.status}'


class WhitelistedUser(models.Model):
    user = models.OneToOneField(User, on_delete=models.PROTECT, related_name='allowed_user')
    allowed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f'{self.user.username} {self.allowed}'


class GlobalSymbol(models.Model):
    class DataSource(models.TextChoices):
        COINGECKO =     'COINGECKO',     'CoinGecko'
        COINMARKETCAP = 'COINMARKETCAP', 'CoinMarketCap'

    cid = models.CharField(max_length=200, unique=True)
    name = models.CharField(max_length=200)
    display = models.CharField(max_length=200)
    base = models.CharField(max_length=200)
    quote = models.CharField(max_length=200, default='USDT')
    data_source = models.CharField(max_length=30, choices=DataSource.choices, default=DataSource.COINGECKO)
    coingecko_response = models.TextField(null=True, blank=True)
    coinmarketcap_response = models.TextField(null=True, blank=True)
    image = models.URLField(null=True, blank=True, max_length=1024, help_text='URL to image of this symbol')
    is_favorite = models.BooleanField(default=False)
    available_markets = models.TextField(default='[]', help_text='JSON string of available markets for this symbol')
    tags = models.TextField(null=True, blank=True, help_text='JSON string of tags for this symbol')
    is_stablecoin = models.BooleanField(null=True, blank=True)

    ath = models.FloatField(null=True, blank=True, help_text='ATH')
    atl = models.FloatField(null=True, blank=True, help_text='ATL')
    ath_date = models.DateTimeField(null=True, blank=True)
    atl_date = models.DateTimeField(null=True, blank=True)
    volume = models.FloatField(null=True, blank=True, help_text='Total volume in USD')
    market_cap = models.FloatField(null=True, blank=True, help_text='Market capitalization in USD')
    circulating_supply = models.FloatField(null=True, blank=True)
    total_supply = models.FloatField(null=True, blank=True)
    max_supply = models.FloatField(null=True, blank=True)
    last_updated = models.DateTimeField(null=True, blank=True, auto_now=True, help_text='Last time this symbol was updated')
    price = models.FloatField(null=True, blank=True, help_text='Current price')
    price_change_24h = models.FloatField(null=True, blank=True, help_text='Price change in the last 24 hours')
    price_change_percentage_24h = models.FloatField(null=True, blank=True, help_text='Price change percentage in the last 24 hours')
    high_24h = models.FloatField(null=True, blank=True, help_text='Highest price in the last 24 hours')
    low_24h = models.FloatField(null=True, blank=True, help_text='Lowest price in the last 24 hours')
    data_updated = models.DateTimeField(null=True, blank=True, help_text='Last time this symbol was updated in the data source')
    supply_ratio = models.FloatField(null=True, blank=True, help_text='Circulating supply / Total supply')
    ath_prox = models.FloatField(null=True, blank=True, help_text='Proximity to all time high')
    ath_ratio = models.FloatField(null=True, blank=True, help_text='ATH / Current price')
    atl_prox = models.FloatField(null=True, blank=True, help_text='Proximity to all time low')
    atl_ratio = models.FloatField(null=True, blank=True, help_text='Current price / ATL')
    volume24h_to_mcap = models.FloatField(null=True, blank=True, help_text='Volume 24H / Market cap')

    @property
    def markets(self):
        return json.loads(self.available_markets)
    
    @property
    def markets_display(self):
        return ', '.join(self.markets)

    @markets.setter
    def markets(self, value):
        self.available_markets = json.dumps(value)

    def add_market(self, market, save=True):
        markets = self.markets
        if market not in markets:
            markets.append(market)
            self.markets = markets
            if save:
                self.save()

    def mainnet_symbols(self):
        return MarketSymbol.objects.filter(symbol=self)

    @property
    def tags_display(self):
        self.tags = self.tags or '[]'
        self.tags = self.tags.replace("'", '"')
        tags = json.loads(self.tags or '[]')
        tags = [t.replace('-', ' ') for t in tags]
        return ', '.join(tags)

    def calculate(self):
        self.supply_ratio = (self.circulating_supply / self.total_supply) if self.circulating_supply and self.total_supply else None
        self.ath_prox = ((self.ath - self.price) / (self.ath - self.atl)) if self.ath != self.atl and self.ath and self.atl and self.price else None
        self.atl_prox = ((self.price - self.atl) / (self.ath - self.atl)) if self.ath != self.atl and self.ath and self.atl and self.price else None
        self.ath_ratio = ((self.ath - self.price) * 100 / self.ath) if self.ath and self.price else None
        self.atl_ratio = (self.price / self.atl) if self.atl and self.price else None
        self.volume24h_to_mcap = (self.volume / self.market_cap) if self.volume and self.market_cap else None

    def set_markets(self, ms=None, save=True):
        if ms:
            market_symbols = ms
        else:
            market_symbols = MarketSymbol.objects.filter(symbol=self)
        current_markets = self.markets
        for ms in market_symbols:
            if ms.market.exchange_name not in current_markets and ms.spot_trading_enabled:
                current_markets.append(ms.market.exchange_name)
        self.markets = current_markets
        if save:
            self.save()

    def save(self, *args, **kwargs):
        self.calculate()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.name} {self.data_source}'
    
    @staticmethod
    def batch_to_json(symbols):
        return [s.to_json() for s in symbols]
    
    def to_json(self):
        return {
            'cid': self.cid,
            'name': self.name,
            'display': self.display,
            'base': self.base,
            'quote': self.quote,
            'data_source': self.data_source,
            'image': self.image,
            'ath': self.ath,
            'atl': self.atl,
            'ath_date': self.ath_date,
            'atl_date': self.atl_date,
            'ath_ratio': self.ath_ratio,
            'atl_ratio': self.atl_ratio,
            'volume': self.volume,
            'market_cap': self.market_cap,
            'circulating_supply': self.circulating_supply,
            'total_supply': self.total_supply,
            'max_supply': self.max_supply,
            'supply_ratio': self.supply_ratio,
            'last_updated': self.last_updated,
            'price_change_24h': self.price_change_24h,
            'price_change_percentage_24h': self.price_change_percentage_24h,
            'high_24h': self.high_24h,
            'low_24h': self.low_24h,
            'data_updated': self.data_updated,
            'ath_prox': self.ath_prox,
            'atl_prox': self.atl_prox,
            'volume24h_to_mcap': self.volume24h_to_mcap,
            'is_favorite': self.is_favorite,
            'markets': self.markets,
            'price': self.price,
        }
