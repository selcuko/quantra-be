from datetime import datetime
import json
import os
import threading
from django.conf import settings
from django.contrib.auth.models import User

import pytz
from typing import Optional
from django.db import models
from cryptography.fernet import Fernet

from strategy import get_strategy


class Market(models.Model):
    class Exchange(models.TextChoices):
        BINANCE = 'BINANCE', 'Binance'
        KUCOIN = 'KUCOIN', 'KuCoin'
        MEXC = 'MEXC', 'MEXC'
    exchange_name = models.CharField(max_length=30)
    friendly_name = models.CharField(max_length=30, null=True, blank=True, help_text='Descriptive name for the config-exchange pair for this market.')
    config_enc = models.TextField(null=True, blank=True, help_text='Config for this market (encrypted).')
    trading_enabled = models.BooleanField(default=False)
    testnet_enabled = models.BooleanField(default=False)
    mainnet_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    symbols: models.QuerySet['Symbol']

    def __str__(self):
        return str(self.friendly_name or self.exchange_name)
    
    def get_interface(self):
        from markets import get_market
        return get_market(self.exchange_name, self.config)

    def is_valid_session_type(self, session_type):
        match session_type:
            case Session.Type.BACKTEST | Session.Type.LIVE_BASIC:
                return True
            case Session.Type.LIVE_SANDBOX:
                return self.testnet_enabled and self.trading_enabled
            case Session.Type.LIVE_MAINNET:
                return self.mainnet_enabled and self.trading_enabled
            case _:
                return False
    @property
    def config(self):
        """Decrypt config_enc and return dict"""
        if not self.config_enc:
            return {}
        key = os.environ.get('SYMKEY', settings.SYMKEY)
        if not key:
            raise ValueError('No SYMKEY set')
        f = Fernet(key)
        return json.loads(f.decrypt(self.config_enc.encode()).decode())
    
    @config.setter
    def config(self, value):
        """Encrypt config and set config_enc"""
        key = os.environ.get('SYMKEY', settings.SYMKEY)
        if not key:
            raise ValueError('No SYMKEY set')
        f = Fernet(key)
        self.config_enc = f.encrypt(json.dumps(value).encode()).decode()

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
        return f'{self.name}@{self.market.exchange_name}'


class Session(models.Model):
    class Type(models.TextChoices):
        BACKTEST     = 'backtest',     'Backtest'
        LIVE_BASIC   = 'live.basic',   'Live Basic'
        LIVE_SANDBOX = 'live.sandbox', 'Live Testnet'
        LIVE_MAINNET = 'live.mainnet', 'Live Mainnet'
    class Status(models.TextChoices):
        ONGOING   = 'ONGOING',   'Ongoing'
        COMPLETED = 'COMPLETED', 'Completed'
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

    session_type = models.CharField(max_length=30, choices=Type.choices)
    freq = models.CharField(max_length=30)
    started = models.DateTimeField(auto_now_add=True)
    ended = models.DateTimeField(null=True, blank=True)
    symbol = models.ForeignKey(Symbol, on_delete=models.PROTECT, related_name='sessions')
    strategy = models.ForeignKey('Strategy', on_delete=models.PROTECT, related_name='sessions', null=True, blank=True)
    strategy_parameters = models.CharField(max_length=256)
    planned_shutdown = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=Status.choices)
    report = models.CharField(max_length=256, null=True, blank=True, help_text='Report file name')
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    last_kline_timestamp = models.DateTimeField(null=True, blank=True)
    signals: models.QuerySet['Signal']
    subscriptions: models.QuerySet['Subscription']
    initial_capital = models.FloatField()
    initial_assets = models.FloatField()
    capital = models.FloatField()
    assets = models.FloatField()
    thread_id = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f'{self.strategy} - {self.symbol} - {self.status}'
    
    @property
    def thread(self):
        threads = threading.enumerate()
        for thread in threads:
            if thread.ident == self.thread_id and thread.is_alive():
                return thread

    def resume(self):
        """Resume an interrupted session."""
        if not self.status == Session.Status.ONGOING:
            raise ValueError(f'Session status should be ONGOING to resume, not {self.status}')
        if not self.pk:
            raise ValueError('Session must be saved before resuming')
        if not self.strategy:
            raise ValueError('Session must have a strategy to resume')
        from livetest import LiveLoop
        ll = LiveLoop(
            symbol=self.symbol.name,
            market=self.symbol.market,
            strategy=get_strategy(self.strategy.name)(),
            capital_limit=self.capital,
            asset_limit=self.assets,
            freq=self.freq,
            end=self.planned_shutdown,
            session=self)
        ll.run()
        return ll

    def stop(self):
        """Stop an ongoing session."""
        if self.status == Session.Status.ONGOING:
            self.status = Session.Status.COMPLETED
            self.planned_shutdown = datetime.now(pytz.utc)
        else:
            raise ValueError(f'Session status should be ONGOING to stop, not {self.status}')


class Strategy(models.Model):
    name = models.CharField(max_length=30)
    description = models.CharField(max_length=256)
    sessions: models.QuerySet[Session]

    def __str__(self):
        return self.name

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
        return self.session.symbol


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
    market_response = models.TextField(null=True, blank=True)

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
        return f'SUB {self.user.username} - {self.session.strategy} - {self.session.symbol.name}'


class Endpoint(models.Model):
    class Type(models.TextChoices):
        TELEGRAM = 'TELEGRAM'
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='endpoints')
    endpoint_type = models.CharField(max_length=30, choices=Type.choices)
    external_id = models.CharField(max_length=256)

    def __str__(self) -> str:
        return f'{self.endpoint_type} {self.external_id}'


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


class WhitelistedUser(models.Model):
    user = models.OneToOneField(User, on_delete=models.PROTECT, related_name='allowed_user')
    allowed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)