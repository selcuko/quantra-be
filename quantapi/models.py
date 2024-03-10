from datetime import datetime
import json
import os
import threading
from django.conf import settings
from django.contrib.auth.models import User
from logger import logger
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
    symbols: models.QuerySet['MarketSymbol']
    key_expiry_date = models.DateTimeField(null=True, blank=True, help_text='Date when the API key for this market will expire.')
    usdt = models.FloatField(null=True, blank=True, help_text='USDT balance in this market')
    assets = models.TextField(null=True, blank=True, help_text='Assets in this market')
    equity = models.FloatField(null=True, blank=True, help_text='Equity in this market')
    prices = models.TextField(null=True, blank=True, help_text='Prices of symbols in this market')
    assets_updated_at = models.DateTimeField(null=True, blank=True, help_text='Last time assets were updated')

    def __str__(self):
        return str(self.friendly_name or self.exchange_name)
    
    def get_interface(self):
        from markets import get_market
        return get_market(self.exchange_name, self.config, self)

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
    def available_capital(self):
        capital_in_sessions = Session.objects.filter(symbol__market=self, status=Session.Status.ONGOING).aggregate(models.Sum('capital'))['capital__sum'] or 0
        return max(self.usdt - capital_in_sessions, 0)

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
        ONGOING   = 'ONGOING',   'Ongoing'
        COMPLETED = 'COMPLETED', 'Completed'
        ERROR     = 'ERROR',     'Error'
        PURGED    = 'PURGED',    'Purged'
        PAUSED    = 'PAUSED',    'Paused'
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
        if not self.status == Session.Status.ONGOING:
            raise ValueError(f'Session status should be ONGOING to resume, not {self.status}')
        if not self.pk:
            raise ValueError('Session must be saved before resuming')
        if not self.strategy:
            raise ValueError('Session must have a strategy to resume')
        from livetest import LiveLoop
        strategy = get_strategy(self.strategy.name)
        ll = LiveLoop(
            symbol=self.symbol.name,
            market=self.symbol.market,
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
        orders = Order.objects.filter(signal__session=self).order_by('-timestamp')[:5]
        orders = orders.filter(status=Order.Status.ERROR)
        return orders.exists()


class Strategy(models.Model):
    name = models.CharField(max_length=30, unique=True)
    description = models.CharField(max_length=256, null=True, blank=True)
    sessions: models.QuerySet[Session]

    class Meta:
        verbose_name_plural = 'Strategies'

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
        ERROR = 'ERROR'
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
    details = models.TextField(null=True, blank=True)
    request = models.TextField(null=True, blank=True)

    def __str__(self) -> str:
        try:
            return f'{self.status} {self.signal.side} {self.signal.session.symbol.name} {self.signal.price}'
        except:
            return f'{self.status} {self.oid}'

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

    def __str__(self) -> str:
        return f'{self.severity} {self.notification_type} {self.state} {self.subject or ""}'
    
    def send(self):
        from telegram import send_message
        if not self.pk:
            self.save()
        message = f'{self.severity} {self.notification_type}\n{self.message}'
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
    payload = models.TextField(null=True, blank=True)
    image = models.URLField(null=True, blank=True, max_length=1024, help_text='URL to image of this symbol')

    ath = models.FloatField(null=True, blank=True)
    atl = models.FloatField(null=True, blank=True)
    ath_date = models.DateTimeField(null=True, blank=True)
    atl_date = models.DateTimeField(null=True, blank=True)
    volume = models.FloatField(null=True, blank=True, help_text='Total volume in USD')
    market_cap = models.FloatField(null=True, blank=True, help_text='Market capitalization in USD')
    circulating_supply = models.FloatField(null=True, blank=True)
    total_supply = models.FloatField(null=True, blank=True)
    max_supply = models.FloatField(null=True, blank=True)
    last_updated = models.DateTimeField(null=True, blank=True, auto_now=True, help_text='Last time this symbol was updated')
    price_change_24h = models.FloatField(null=True, blank=True, help_text='Price change in the last 24 hours')
    price_change_percentage_24h = models.FloatField(null=True, blank=True, help_text='Price change percentage in the last 24 hours')
    high_24h = models.FloatField(null=True, blank=True, help_text='Highest price in the last 24 hours')
    low_24h = models.FloatField(null=True, blank=True, help_text='Lowest price in the last 24 hours')
    data_updated = models.DateTimeField(null=True, blank=True, help_text='Last time this symbol was updated in the data source')
    supply_ratio = models.FloatField(null=True, blank=True, help_text='Circulating supply / Total supply')
    ath_prox = models.FloatField(null=True, blank=True, help_text='Proximity to all time high')
    atl_prox = models.FloatField(null=True, blank=True, help_text='Proximity to all time low')

    @property
    def price(self):
        return json.loads(self.payload).get('current_price')

    def calculate(self):
        self.supply_ratio = (self.circulating_supply / self.total_supply) if self.circulating_supply and self.total_supply else None
        self.ath_prox = ((self.ath - self.price) / (self.ath - self.atl)) if self.ath != self.atl and self.ath and self.atl and self.price else None
        self.atl_prox = ((self.price - self.atl) / (self.ath - self.atl)) if self.ath != self.atl and self.ath and self.atl and self.price else None

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
            'payload': self.payload,
            'image': self.image,
            'ath': self.ath,
            'atl': self.atl,
            'ath_date': self.ath_date,
            'atl_date': self.atl_date,
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
            'supply_ratio': self.supply_ratio,
        }
