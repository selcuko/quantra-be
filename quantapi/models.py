from datetime import datetime
import json

import pytz
from typing import List, Optional
from django.db import models
from django.contrib.auth.models import User

from strategy import get_strategy


class Market(models.Model):
    class Exchange(models.TextChoices):
        BINANCE = 'BINANCE', 'Binance'
        KUCOIN = 'KUCOIN', 'KuCoin'
        MEXC = 'MEXC', 'MEXC'
    exchange_name = models.CharField(max_length=30)
    friendly_name = models.CharField(max_length=30, null=True, blank=True, help_text='Descriptive name for the config-exchange pair for this market.')
    config_name = models.CharField(max_length=30, null=True, blank=True, help_text='Name of key in config file for this market.')
    trading_enabled = models.BooleanField(default=False)
    testnet_enabled = models.BooleanField(default=False)
    mainnet_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    symbols: models.QuerySet['Symbol']

    def __str__(self):
        return str(self.friendly_name or self.exchange_name)
    
    def get_interface(self):
        from markets import get_market
        return get_market(self.exchange_name, self.config_name)

    def is_valid_session_type(self, session_type):
        match session_type:
            case Session.Type.BACKTEST, Session.Type.LIVE_BASIC:
                return True
            case Session.Type.LIVE_SANDBOX:
                return self.testnet_enabled and self.trading_enabled
            case Session.Type.LIVE_MAINNET:
                return self.mainnet_enabled and self.trading_enabled
            case _:
                return False


class Symbol(models.Model):
    market = models.ForeignKey(Market, on_delete=models.PROTECT, related_name='symbols')
    base = models.CharField(max_length=10)
    quote = models.CharField(max_length=10)
    name = models.CharField(max_length=30)
    base_precision = models.IntegerField(null=True, blank=True, help_text='Number of decimal places for base currency')
    quote_precision = models.IntegerField(null=True, blank=True, help_text='Number of decimal places for quote currency')
    spot_trading_enabled = models.BooleanField(default=True, help_text='Spot trading enabled for this symbol in related market')
    margin_trading_enabled = models.BooleanField(default=False, help_text='Margin trading enabled for this symbol in related market')
    sessions: models.QuerySet['Session']

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
            return f'{self.name}@Unbound'


class Session(models.Model):
    class Type(models.TextChoices):
        BACKTEST     = 'backtest',     'Backtest'
        LIVE_BASIC   = 'live.basic',   'Live Basic'
        LIVE_SANDBOX = 'live.sandbox', 'Live Testnet'
        LIVE_MAINNET = 'live.mainnet', 'Live Mainnet'
    class Status(models.TextChoices):
        ONGOING   = 'ONGOING',   'Ongoing'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'
        ERROR     = 'ERROR',     'Error'
        PURGED    = 'PURGED',    'Purged'
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

    class Strategy(models.TextChoices):
        V1 = 'v1', 'Strategy v1: Lisa (PandasTA)'
        V2 = 'v2', 'Strategy v2: Lisa (NumPy)'

    session_type = models.CharField(max_length=30, choices=Type.choices)
    freq = models.CharField(max_length=30)
    started = models.DateTimeField(auto_now_add=True)
    ended = models.DateTimeField(null=True, blank=True)
    symbol = models.ForeignKey(Symbol, on_delete=models.PROTECT, related_name='sessions')
    strategy_name = models.CharField(max_length=30, choices=Strategy.choices)
    strategy_parameters = models.CharField(max_length=256)
    planned_shutdown = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=Status.choices)
    report = models.CharField(max_length=256, null=True, blank=True, help_text='Report file name')
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    signals: models.QuerySet['Signal']
    subscriptions: models.QuerySet['Subscription']
    live_loop_cache: Optional['LiveLoopCache']
    initial_capital = models.FloatField()
    initial_assets = models.FloatField()
    capital = models.FloatField()
    assets = models.FloatField()

    def __str__(self):
        return f'{self.strategy_name} - {self.symbol} - {self.status}'

    def notify(self, message):
        print(f'Notifying {self.subscriptions.count()} subscribers: {message}')

    def notify_signal(self, signal):
        return self.notify(str(signal))

    def notify_order(self, order):
        return self.notify(str(order))

    def notify_complete(self, summary):
        return self.notify(str(summary))

    def profit(self):
        orders:List[Order] = []
        for signal in self.signals.all():
            try:
                if signal.order:
                    orders.append(signal.order)
            except:
                pass
        if not orders:
            return 0.
        if orders[-1].signal.side == 'SELL':
            return orders[-1].deal_funds - orders[0].deal_funds
        elif len(orders) > 1:
            return orders[-2].deal_funds - orders[0].deal_funds
        return 0.

    def equity(self):
        orders:List[Order] = []
        for signal in self.signals.all():
            try:
                if signal.order:
                    orders.append(signal.order)
            except:
                pass
        if not orders:
            return 0.
        else:
            price = orders[-1].price or orders[-1].signal.price
            return orders[-1].deal_funds + orders[-1].deal_size * price

    def orders(self):
        orders:List[Order] = []
        for signal in self.signals.all():
            try:
                if signal.order:
                    orders.append(signal.order)
            except:
                pass
        return orders

    @property
    def cache(self):
        if hasattr(self, 'live_loop_cache') and self.live_loop_cache is not None:
            return self.live_loop_cache
        return None

    def resume(self):
        """Resume a session that was interrupted by a shutdown or error."""
        if not self.status == Session.Status.ONGOING:
            raise ValueError('Cannot resume non-ongoing session')
        if not self.pk:
            raise ValueError('Cannot resume session without id')
        from livetest import LiveLoop
        ll = LiveLoop(
            symbol=self.symbol.name,
            market=self.symbol.market.get_interface(),
            strategy=get_strategy(self.strategy_name)(),
            capital_limit=self.initial_capital,
            asset_limit=self.initial_assets,
            freq=self.freq,
            end=self.planned_shutdown,
            session=self,
            market_id_for_symbol=self.symbol.market.pk,
        )
        ll.run()
        if not self.cache:
            cache = LiveLoopCache.objects.create(
                session=self,
                status='RESUME',
                created=datetime.now(pytz.UTC),
                last_started=datetime.now(pytz.UTC),
                thread_id=ll.thread.ident if ll.thread else None,
            )
        else:
            cache = self.cache
            cache.status = 'RESUME'
            cache.last_started = datetime.now(pytz.UTC)
            cache.thread_id = (ll.thread.ident if ll.thread else None)
            cache.save()
        return ll

    @classmethod
    def is_valid_freq(cls, f):
        return f in cls.Freq.values


class Signal(models.Model):
    class Side(models.TextChoices):
        BUY = 'BUY'
        SELL = 'SELL'
    session = models.ForeignKey(Session, on_delete=models.PROTECT, related_name='signals')
    timestamp = models.DateTimeField()
    side = models.CharField(max_length=30, choices=Side.choices)
    price = models.FloatField()
    raw = models.CharField(max_length=512)
    order: Optional[models.OneToOneField['Order']]

    def __str__(self) -> str:
        return f'{self.side} {self.session.symbol.name} {self.price}'
    
    @property
    def symbol(self):
        try:
            return self.session.symbol
        except:
            return None
    
    @property
    def display_price(self):
        if self.price > 0:
            return self.price
        if self.raw and self.raw.startswith('{'):
            try:
                price = json.loads(self.raw).get('close')
                if price:
                    return price
            except:
                pass
        return 0.


class Order(models.Model):
    class Type(models.TextChoices):
        MARKET = 'MARKET'
        LIMIT = 'LIMIT'
    class Status(models.TextChoices):
        OPEN = 'OPEN'
        FILLED = 'FILLED'
        CANCELLED = 'CANCELLED'
        REJECTED = 'REJECTED'
        EXPIRED = 'EXPIRED'
    oid = models.CharField(max_length=256, unique=True, null=True, blank=True)
    client_oid = models.CharField(max_length=256, unique=True, null=True, blank=True)
    deal_size = models.FloatField(help_text='Amount of quote currency in this order (e.g. BTC)')
    price = models.FloatField(help_text='Price represented as (price of base)/(price of quote)')
    deal_funds = models.FloatField(help_text='Amount of base currency in this order (e.g. USDT)')
    funds = models.FloatField(help_text='Amount of base currency of this order initially placed with')
    order_type = models.CharField(max_length=30, choices=Type.choices)
    signal = models.OneToOneField(Signal, on_delete=models.PROTECT, related_name='order')
    timestamp = models.DateTimeField()
    status = models.CharField(max_length=30, choices=Status.choices)
    force = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f'{self.status} {self.signal.side} {self.signal.session.symbol.name} {self.signal.price}'

    def refresh_from_market(self, market_interface):
        if not self.oid:
            raise ValueError('Cannot refresh order without oid')
        order = market_interface.get_order(self.signal.session.symbol, self.oid)
        self.status = order.status
        self.deal_funds = order.deal_funds
        self.price = order.price
        self.deal_size = order.deal_size
        self.funds = order.funds
        self.order_type = order.order_type
        self.timestamp = order.timestamp
        self.client_oid = order.client_oid
        self.save()
    
    @property
    def symbol(self):
        try:
            return self.signal.symbol
        except:
            return None
    
    @property
    def display_price(self):
        if self.price > 0:
            return self.price
        return self.deal_funds / self.deal_size


class Subscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='subscriptions')
    session = models.ForeignKey(Session, on_delete=models.PROTECT, related_name='subscriptions')

    def __str__(self) -> str:
        return f'SUB {self.user.username} - {self.session.strategy_name} - {self.session.symbol.name}'


class Endpoint(models.Model):
    class Type(models.TextChoices):
        TELEGRAM = 'TELEGRAM'
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='endpoints')
    endpoint_type = models.CharField(max_length=30, choices=Type.choices)
    external_id = models.CharField(max_length=256)

    def __str__(self) -> str:
        return f'{self.endpoint_type} {self.external_id}'


class LiveLoopCache(models.Model):
    class Meta:
        verbose_name = 'Live Loop Cache'
        verbose_name_plural = 'Live Loop Cache'
    session = models.OneToOneField(Session, on_delete=models.PROTECT, related_name='live_loop_cache', null=True, blank=True)
    created = models.DateTimeField()
    last_started = models.DateTimeField()
    last_ended = models.DateTimeField(null=True, blank=True)
    thread_id = models.IntegerField()
    status = models.CharField(max_length=30)

    def __str__(self) -> str:
        return f'LLC {self.session}'
