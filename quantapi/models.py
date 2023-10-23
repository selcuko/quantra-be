from typing import Optional
from django.db import models


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
    session_type = models.CharField(max_length=30, choices=Type.choices)
    freq = models.CharField(max_length=30)
    started = models.DateTimeField(auto_now_add=True)
    ended = models.DateTimeField(null=True, blank=True)
    symbol = models.ForeignKey(Symbol, on_delete=models.PROTECT, related_name='sessions')
    strategy_name = models.CharField(max_length=30)
    strategy_parameters = models.CharField(max_length=256)
    planned_shutdown = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=Status.choices)
    report = models.CharField(max_length=256, null=True, blank=True, help_text='Report file name')
    last_heartbeat = models.DateTimeField(auto_now=True)
    signals: models.QuerySet['Signal']
    subscriptions: models.QuerySet['Subscription']

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
        total = 0
        for signal in self.signals.all():
            try:
                total += signal.order.deal_funds
            except:
                continue
        return total

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


class Order(models.Model):
    class Type(models.TextChoices):
        MARKET = 'MARKET'
        LIMIT = 'LIMIT'
    class Status(models.TextChoices):
        OPEN = 'OPEN'
        FILLED = 'FILLED'
        CANCELLED = 'CANCELLED'
        REJECTED = 'REJECTED'
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

    def save(self, *args, **kwargs):
        if self.funds < self.deal_funds:
            raise ValueError('Cannot save order with funds < size')
        super().save(*args, **kwargs)
    
    @property
    def symbol(self):
        try:
            return self.signal.symbol
        except:
            return None


class User(models.Model):
    name = models.CharField(max_length=30)
    email = models.EmailField()
    password = models.CharField(max_length=256)

    def __str__(self) -> str:
        return self.name


class Subscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='subscriptions')
    session = models.ForeignKey(Session, on_delete=models.PROTECT, related_name='subscriptions')

    def __str__(self) -> str:
        return f'SUB {self.user.name} - {self.session.strategy_name} - {self.session.symbol.name}'


class Endpoint(models.Model):
    class Type(models.TextChoices):
        TELEGRAM = 'TELEGRAM'
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='endpoints')
    endpoint_type = models.CharField(max_length=30, choices=Type.choices)
    external_id = models.CharField(max_length=256)

    def __str__(self) -> str:
        return f'{self.endpoint_type} {self.external_id}'
