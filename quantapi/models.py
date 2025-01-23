from functools import cached_property
import json
import typing
from datetime import datetime, timedelta
from decimal import Decimal

import pytz
from cryptography.fernet import Fernet
from django.conf import settings
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models

from logger import logger
from relay.models import Issue

if typing.TYPE_CHECKING:
    from markets import IMarket


class Market(models.Model):
    class Meta:
        ordering = ['exchange_name']
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
    icon = models.URLField(null=True, blank=True, help_text='URL of the exchange icon')

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

    def fields(self):
        access_key = { 'name': 'access_key', 'display_name': 'Access Key' }
        api_key = { 'name': 'api_key', 'display_name': 'API Key' }
        api_secret = { 'name': 'api_secret', 'display_name': 'API Secret' }
        api_passphrase = { 'name': 'api_passphrase', 'display_name': 'API Passphrase' }
        fields = []
        match self.exchange_name.lower():
            case 'binance' | 'bybit' | 'gateio':
                fields = [api_key, api_secret]
            case 'kucoin':
                fields = [api_key, api_secret, api_passphrase]
            case 'mexc':
                fields = [api_secret, access_key]
            case 'okx':
                fields = [api_key, api_secret, api_passphrase]
            case _:
                fields = []
        return fields

    def get_interface(self):
        """Returns a public interface for this market."""
        from markets import get_market
        return get_market(self.exchange_name, {}, market=self)

    def __str__(self):
        return self.exchange_name

    @property
    def display_name(self):
        return self.Exchange(self.exchange_name).label


def three_months_later():
    return datetime.now(pytz.utc) + timedelta(days=90)

class MarketCredentials(models.Model):
    market     = models.ForeignKey(Market, on_delete=models.PROTECT, related_name='credentials')
    encrypted  = models.TextField(help_text='Encrypted credentials. This field is encrypted automatically if it contains valid JSON data.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(default=three_months_later)
    notified_at = models.DateTimeField(null=True, blank=True, help_text='Last time owner was notified about expiration')
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
                data = json.dumps(json.loads(self.encrypted))
                fernet = Fernet(settings.SYMKEY)
                self.encrypted = fernet.encrypt(data.encode()).decode()
            except json.JSONDecodeError:
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
        except json.JSONDecodeError:
            logger.error(f'Could not decrypt credentials for {self.market.exchange_name}', exc_info=True)
            return {}


class MarketAccount(models.Model):
    market      = models.ForeignKey(Market, on_delete=models.PROTECT, related_name='accounts')
    credentials = models.ForeignKey(MarketCredentials, on_delete=models.PROTECT, related_name='accounts')
    equity     = models.FloatField(default=0, help_text='Total USDT equity in this account')
    capital    = models.FloatField(default=0, help_text='Total USDT capital in this account')
    assets     = models.TextField(default='{}', help_text='Assets in this account')
    last_cache = models.DateTimeField(null=True, blank=True, help_text='Last time equity/assets were updated')
    issues     = GenericRelation(Issue)

    def __str__(self):
        return f'MarketAccount <{self.pk}>'

    def save(self, *args, **kwargs):
        if self.market != self.credentials.market:
            raise ValueError('Market and credentials should be for the same market.')
        super().save(*args, **kwargs)

    def get_interface(self):
        from markets import get_market
        return get_market(self.market.exchange_name, self.credentials.decrypted, self)

    @property
    def available_capital(self):
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

    def active_issues(self):
        return self.issues.filter(status=Issue.Status.ACTIVE)

    def refresh(self, interface:'IMarket|None'=None, force=False):
        interface = interface or self.get_interface()
        if self.last_cache and timezone.now() - self.last_cache < timedelta(minutes=1) and not force:
            return
        interface.get_account()
        return


class MarketSymbolMetrics(models.Model):
    symbol = models.OneToOneField('MarketSymbol', on_delete=models.CASCADE, related_name='metrics')

    # first hand metrics - from data providers (e.g. coingecko) or exchanges
    volume = models.FloatField(null=True, blank=True, help_text='Volume in USD, rolling 24 hours')
    market_cap = models.FloatField(null=True, blank=True, help_text='Market capitalization in USD')
    market_cap_change_24h = models.FloatField(null=True, blank=True, help_text='Market cap change in the last 24 hours')
    market_cap_change_percentage_24h = models.FloatField(null=True, blank=True, help_text='Market cap change percentage in the last 24 hours')
    ath = models.FloatField(null=True, blank=True, help_text='All time high in USD', verbose_name='ATH')
    atl = models.FloatField(null=True, blank=True, help_text='All time low in USD', verbose_name='ATL')
    ath_date = models.DateTimeField(null=True, blank=True, help_text='Date of all time high', verbose_name='ATH Date')
    atl_date = models.DateTimeField(null=True, blank=True, help_text='Date of all time low', verbose_name='ATL Date')
    ath_prox = models.FloatField(null=True, blank=True, help_text='Proximity to all time high (0-1)', verbose_name='ATH Proximity')
    atl_prox = models.FloatField(null=True, blank=True, help_text='Proximity to all time low (0-1)', verbose_name='ATL Proximity')
    ath_ratio = models.FloatField(null=True, blank=True, help_text='ATH / Current price', verbose_name='ATH Ratio')
    atl_ratio = models.FloatField(null=True, blank=True, help_text='Current price / ATL', verbose_name='ATL Ratio')
    circulating_supply = models.FloatField(null=True, blank=True)
    total_supply = models.FloatField(null=True, blank=True)
    max_supply = models.FloatField(null=True, blank=True)
    price = models.FloatField(null=True, blank=True, help_text='Current price in USD')
    price_change_24h = models.FloatField(null=True, blank=True, help_text='Price change in the last 24 hours (rolling)')
    price_change_percentage_24h = models.FloatField(null=True, blank=True)
    price_high_24h = models.FloatField(null=True, blank=True, help_text='Highest price in the last 24 hours')
    price_low_24h = models.FloatField(null=True, blank=True, help_text='Lowest price in the last 24 hours')

    # derived metrics
    supply_ratio = models.FloatField(null=True, blank=True, help_text='Circulating supply / Total supply')
    volume24h_to_mcap = models.FloatField(null=True, blank=True, help_text='Volume 24H / Market cap')
    is_stablecoin = models.BooleanField(default=False)

    raw_payload = models.TextField(null=True, blank=True)
    last_updated = models.DateTimeField(null=True, blank=True, auto_now=True, help_text='Last time this symbol was updated in our system')
    data_updated = models.DateTimeField(null=True, blank=True, help_text='Last time this symbol was fetched from the data source')

    def __str__(self):
        return f'{self.symbol!r} Metrics'

    def calculate(self):
        self.supply_ratio = (self.circulating_supply / self.total_supply) if self.circulating_supply and self.total_supply else None
        self.ath_prox = ((self.ath - self.price) / (self.ath - self.atl)) if self.ath != self.atl and self.ath and self.atl and self.price else None
        self.atl_prox = ((self.price - self.atl) / (self.ath - self.atl)) if self.ath != self.atl and self.ath and self.atl and self.price else None
        self.ath_ratio = ((self.ath - self.price) * 100 / self.ath) if self.ath and self.price else None
        self.atl_ratio = (self.price / self.atl) if self.atl and self.price else None
        self.volume24h_to_mcap = (self.volume / self.market_cap) if self.volume and self.market_cap else None


class MarketSymbol(models.Model):
    class ContractType(models.TextChoices):
        SPOT = 'SPOT', 'Spot'
        FUTURES = 'FUTURES', 'Futures'
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name', 'market', 'contract_type'], name='unique_symbol')
        ]
        ordering = ['market__exchange_name', 'name']
    symbol = models.ForeignKey('GlobalSymbol', on_delete=models.SET_NULL, related_name='symbols', null=True, blank=True)
    market = models.ForeignKey(Market, on_delete=models.PROTECT, related_name='symbols')
    base = models.CharField(max_length=30, db_index=True)
    quote = models.CharField(max_length=30, db_index=True)
    name = models.CharField(max_length=60, db_index=True)
    base_precision = models.DecimalField(null=True, blank=True, max_digits=20, decimal_places=10, help_text='Number of decimal places for base currency')
    quote_precision = models.DecimalField(null=True, blank=True, max_digits=20, decimal_places=10, help_text='Number of decimal places for quote currency')
    spot_trading_enabled = models.BooleanField(default=True, help_text='Spot trading enabled for this symbol in related market')
    margin_trading_enabled = models.BooleanField(default=False, help_text='Margin trading enabled for this symbol in related market')
    details = models.TextField(null=True, blank=True, help_text='JSON string of symbol detail from market')
    contract_type = models.CharField(max_length=30, choices=ContractType.choices, default=ContractType.SPOT)
    available_contracts = models.TextField(default='', help_text='Available contracts for this symbol')
    metrics: models.OneToOneField['MarketSymbolMetrics | None']
    # volume = models.FloatField(null=True, blank=True, help_text='Volume in USD, rolling 24 hours')

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
        return f'{self.name} {self.market.exchange_name}-{self.contract_type}'

    def key(self):
        return f'{self.name}.{self.market.exchange_name}.{self.contract_type}'.lower()

    def filters(self):
        return self.market.filters(self)

    @cached_property
    def volume(self):
        # XXX revisit
        if not self.symbol:
            return
        market_map = {
            'gate': 'GATEIO',
            'mxc': 'MEXC',
            'binance': 'BINANCE',
            'kucoin': 'KUCOIN',
            'okex': 'OKX',
            'bybit_spot': 'BYBIT',
        }
        payload = json.loads(self.symbol.coingecko_response or '{}')
        for ticker in payload.get('tickers', []):
            if ticker['base'] != self.base or ticker['target'] != self.quote:
                continue
            if market_map.get(ticker['market']['identifier']) != self.market.exchange_name:
                continue
            return ticker['converted_volume']['usd']


class GlobalSymbol(models.Model):
    class Meta:
        ordering = ['-volume']

    class DataSource(models.TextChoices):
        COINGECKO =     'COINGECKO',     'CoinGecko'
        COINMARKETCAP = 'COINMARKETCAP', 'CoinMarketCap'

    cid = models.CharField(max_length=200, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    display = models.CharField(max_length=200)
    base = models.CharField(max_length=200, db_index=True)
    description = models.TextField(null=True, blank=True)
    homepage = models.URLField(null=True, blank=True, max_length=1024)
    blockchain_site = models.JSONField(null=True, blank=True, help_text='Explorers')
    whitepaper = models.URLField(null=True, blank=True, max_length=1024)
    official_forum_url = models.JSONField(null=True, blank=True)
    chat_url = models.JSONField(null=True, blank=True)
    announcement_url = models.JSONField(null=True, blank=True)
    twitter_screen_name = models.CharField(max_length=200, null=True, blank=True)
    facebook_username = models.CharField(max_length=200, null=True, blank=True)
    subreddit_url = models.URLField(null=True, blank=True, max_length=1024)
    github_repo_url = models.JSONField(null=True, blank=True)
    genesis_date = models.DateField(null=True, blank=True)
    sentiment_votes_up_percentage = models.FloatField(null=True, blank=True)
    sentiment_votes_down_percentage = models.FloatField(null=True, blank=True)
    watchlist_portfolio_users = models.IntegerField(null=True, blank=True)
    market_cap_rank = models.IntegerField(null=True, blank=True)
    twitter_followers = models.IntegerField(null=True, blank=True)
    developer_data = models.JSONField(null=True, blank=True, help_text='Developer data from Github page')
    volume_distribution = models.JSONField(null=True, blank=True, help_text='Volume distribution by exchanges')
    bid_ask_spread_percentage_distribution = models.JSONField(null=True, blank=True, help_text='Bid/Ask spread percentage distribution by exchanges')

    data_source = models.CharField(max_length=30, choices=DataSource.choices, default=DataSource.COINGECKO)
    coingecko_response = models.TextField(null=True, blank=True)
    coinmarketcap_response = models.TextField(null=True, blank=True)
    image = models.URLField(null=True, blank=True, max_length=1024, help_text='URL to image of this symbol')
    tags = models.ManyToManyField('Tag', related_name='symbols')
    markets = models.JSONField(null=True, blank=True, help_text='List of markets where this symbol is traded')

    volume = models.FloatField(null=True, blank=True, db_index=True, help_text='Volume in USD, rolling 24 hours')
    market_cap = models.FloatField(null=True, blank=True, db_index=True, help_text='Market capitalization in USD')
    market_cap_change_24h = models.FloatField(null=True, blank=True, help_text='Market cap change in the last 24 hours')
    market_cap_change_percentage_24h = models.FloatField(null=True, blank=True, help_text='Market cap change percentage in the last 24 hours')
    ath = models.FloatField(null=True, blank=True, help_text='All time high in USD', verbose_name='ATH')
    atl = models.FloatField(null=True, blank=True, help_text='All time low in USD', verbose_name='ATL')
    ath_date = models.DateTimeField(null=True, blank=True, help_text='Date of all time high', verbose_name='ATH Date')
    atl_date = models.DateTimeField(null=True, blank=True, help_text='Date of all time low', verbose_name='ATL Date')
    ath_prox = models.FloatField(null=True, blank=True, help_text='Proximity to all time high (0-1)', verbose_name='ATH Proximity')
    atl_prox = models.FloatField(null=True, blank=True, help_text='Proximity to all time low (0-1)', verbose_name='ATL Proximity')
    ath_ratio = models.FloatField(null=True, blank=True, help_text='ATH / Current price', verbose_name='ATH Ratio')
    atl_ratio = models.FloatField(null=True, blank=True, help_text='Current price / ATL', verbose_name='ATL Ratio')
    circulating_supply = models.FloatField(null=True, blank=True)
    total_supply = models.FloatField(null=True, blank=True)
    max_supply = models.FloatField(null=True, blank=True)
    price = models.FloatField(null=True, blank=True, help_text='Current price in USD')
    price_change_24h = models.FloatField(null=True, blank=True, help_text='Price change in the last 24 hours (rolling)')
    price_change_percentage_24h = models.FloatField(null=True, blank=True)
    price_high_24h = models.FloatField(null=True, blank=True, help_text='Highest price in the last 24 hours')
    price_low_24h = models.FloatField(null=True, blank=True, help_text='Lowest price in the last 24 hours')

    fully_diluted_valuation = models.FloatField(null=True, blank=True, help_text='Fully diluted valuation in USD')
    market_cap_fdv_ratio = models.FloatField(null=True, blank=True, help_text='Market cap / Fully diluted valuation')
    price_change_percentage_7d = models.FloatField(null=True, blank=True, help_text='Price change percentage in the last 7 days')
    price_change_percentage_14d = models.FloatField(null=True, blank=True, help_text='Price change percentage in the last 14 days')
    price_change_percentage_30d = models.FloatField(null=True, blank=True, help_text='Price change percentage in the last 30 days')
    price_change_percentage_60d = models.FloatField(null=True, blank=True, help_text='Price change percentage in the last 60 days')
    price_change_percentage_200d = models.FloatField(null=True, blank=True, help_text='Price change percentage in the last 200 days')
    price_change_percentage_1y = models.FloatField(null=True, blank=True, help_text='Price change percentage in the last 1 year')

    supply_ratio = models.FloatField(null=True, blank=True, help_text='Circulating supply / Total supply')
    volume24h_to_mcap = models.FloatField(null=True, blank=True, help_text='Volume 24H / Market cap')
    is_stablecoin = models.BooleanField(default=False)

    raw_payload = models.TextField(null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True, help_text='Last time this symbol was updated in our system')
    data_updated = models.DateTimeField(auto_now_add=True, null=True, help_text='Last time this symbol was fetched from the data source')

    symbols: models.QuerySet[MarketSymbol]

    @property
    def display_name(self):
        if self.display:
            return self.display
        payload = json.loads(self.coingecko_response or '{}')
        return payload.get('name')

    @property
    def spot_symbols(self):
        return self.symbols.filter(symbol=self, contract_type=MarketSymbol.ContractType.SPOT)

    @property
    def circulating_percent(self):
        try:
            return (self.circulating_supply / self.max_supply) * 100 if self.circulating_supply and self.max_supply else 0
        except (ZeroDivisionError, TypeError):
            return 0

    def __str__(self):
        return f'{self.base} {self.data_source}'

    def refresh(self):
        from metrichub import update_symbol
        update_symbol(self)

    @cached_property
    def cex_volume(self):
        return self.volume_distribution

    @property
    def updated_timedelta(self):
        try: timezone.now() - self.data_updated if self.data_updated else timedelta.max
        except: return timedelta.max

    def calculate(self):
        self.supply_ratio = (self.circulating_supply / self.total_supply) if self.circulating_supply and self.total_supply else None
        self.ath_prox = ((self.ath - self.price) / (self.ath - self.atl)) if self.ath != self.atl and self.ath and self.atl and self.price else None
        self.atl_prox = ((self.price - self.atl) / (self.ath - self.atl)) if self.ath != self.atl and self.ath and self.atl and self.price else None
        self.ath_ratio = ((self.ath - self.price) * 100 / self.ath) if self.ath and self.price else None
        self.atl_ratio = (self.price / self.atl) if self.atl and self.price else None
        self.volume24h_to_mcap = (self.volume / self.market_cap) if self.volume and self.market_cap else None

    def save(self, *args, **kwargs):
        self.calculate()
        super().save(*args, **kwargs)


class Tag(models.Model):
    '''M:M relationship with GlobalSymbol'''
    name = models.CharField(max_length=100, unique=True)
    display = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    is_ecosystem = models.BooleanField(default=False)
    is_chain = models.BooleanField(default=False)
    is_portfolio = models.BooleanField(default=False)
    weight = models.IntegerField(default=0)
    symbols: models.QuerySet[GlobalSymbol]
    volume = models.FloatField(null=True, blank=True)
    market_cap = models.FloatField(null=True, blank=True)
    market_cap_change_24h = models.FloatField(null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True, help_text='Last time this tag was updated in our system')
    data_updated = models.DateTimeField(null=True, blank=True, help_text='Last time this tag was fetched from the data source')

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.name.endswith('-ecosystem'):
            self.is_ecosystem = True
        if self.name.endswith('-chain'):
            self.is_chain = True
        if self.name.endswith('-portfolio'):
            self.is_portfolio = True
        if not self.weight and self.pk:
            self.weight = self.symbols.count()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = 'Tags'
        ordering = ['-weight', 'name']


class ContactForm(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    user_agent = models.CharField(max_length=256, null=True, blank=True)

    def __str__(self):
        return f'{self.name} <{self.email}>'
