import json
from rest_framework import serializers
from quantapi.models import (ContactForm, GlobalSymbol, GlobalSymbolMetrics, GroupOrder, Market, MarketAccount, MarketCredentials, 
                             MarketSymbol, Order, Session, SessionGroup, 
                             Signal, Strategy, Subscription, Tag, TagMetrics)
from quantapi.validations import validate_order_payload, validate_symbol_against_market


class MarketSerializer(serializers.HyperlinkedModelSerializer):
    prices = serializers.HyperlinkedIdentityField(view_name='market-prices')

    class Meta:
        model = Market
        fields = ['id', 'url', 'exchange_name', 'prices_updated', 'prices', 'icon', 'display_name']


class MarketAccountSerializer(serializers.HyperlinkedModelSerializer):
    assets = serializers.SerializerMethodField()
    exchange_name = serializers.CharField(source='market.exchange_name')
    owner = serializers.CharField(source='credentials.owner')
    active = serializers.BooleanField(source='credentials.active')
    internal = serializers.BooleanField(source='credentials.internal')
    prices_updated = serializers.DateTimeField(source='market.prices_updated', allow_null=True)
    credentials_expires_at = serializers.DateTimeField(source='credentials.expires_at', allow_null=True)

    class Meta:
        model = MarketAccount
        fields = ['id', 'market', 'exchange_name', 'equity', 'capital', 'assets', 'last_cache', 
                  'owner', 'active', 'internal', 'prices_updated', 'url', 'credentials_expires_at']

    def get_assets(self, obj):
        assets = json.loads(obj.assets or '{}')
        prices = json.loads(obj.market.prices or '{}')
        payload = {}

        symbols_map = {
            symbol.base: symbol.symbol.image if symbol.symbol else None 
            for symbol in obj.market.symbols.all()
        }

        for k, v in assets.items():
            price = prices.get(f'{k}-USDT', 0)
            if k == 'USDT' or v <= 0:
                continue
            payload[k] = {
                'amount': v,
                'price': price,
                'value': (v * price) or None,
                'icon': symbols_map.get(k),
            }
        return payload


class NewAccountSerializer(serializers.Serializer):
    access_key = serializers.CharField(required=False)
    api_key = serializers.CharField(required=False)
    api_secret = serializers.CharField(required=False)
    api_passphrase = serializers.CharField(required=False)
    owner = serializers.CharField()
    internal = serializers.BooleanField(default=False)
    active = serializers.BooleanField(default=True)
    market = serializers.PrimaryKeyRelatedField(queryset=Market.objects.all())

    def validate(self, data):
        super().validate(data)
        market: Market = data['market']
        fields = market.fields()
        secrets = {}
        for field in fields:
            if not data.get(field['name']):
                raise serializers.ValidationError(f'{field["name"]} is required for {market.exchange_name}')
            secrets[field['name'].upper()] = data.pop(field['name'])
        encrypted = json.dumps(secrets)
        creds = MarketCredentials.objects.create(encrypted=encrypted, **data)
        acct = MarketAccount.objects.get(credentials=creds)
        try:
            acct.get_interface()
        except Exception as e:
            acct.delete()
            creds.delete()
            raise serializers.ValidationError(detail=f'Failed to authenticate with the provided credentials: {e!r}')
        data['account'] = acct
        data['credentials'] = creds
        return data


class InlineMarketAccountSerializer(serializers.HyperlinkedModelSerializer):
    market = serializers.CharField(source='market.exchange_name')
    owner = serializers.CharField(source='credentials.owner')
    active = serializers.BooleanField(source='credentials.active')
    internal = serializers.BooleanField(source='credentials.internal')

    class Meta:
        model = MarketAccount
        fields = ['id', 'market', 'owner', 'active', 'internal', 'url']


class MarketSymbolSerializer(serializers.HyperlinkedModelSerializer):
    market = MarketSerializer()
    exchange_name = serializers.CharField(source='market.exchange_name')
    icon = serializers.URLField(source='symbol.image', allow_null=True)
    price = serializers.SerializerMethodField()
    price_updated = serializers.DateTimeField(source='market.prices_updated', allow_null=True)
    cid = serializers.CharField(source='symbol.cid', allow_null=True)
    class Meta:
        model = MarketSymbol
        fields = ['symbol', 'market', 'exchange_name', 'name', 'base', 'quote', 'base_precision', 'quote_precision', 
                  'spot_trading_enabled', 'icon', 'price', 'price_updated', 'id', 'url', 'cid', 'contract_type', 'available_contracts', 'volume']

    def get_price(self, obj):
        prices = json.loads(obj.market.prices or '{}')
        return prices.get(obj.name)


class InlineMarketSymbolSerializer(serializers.HyperlinkedModelSerializer):
    icon = serializers.URLField(source='symbol.image', allow_null=True)
    market = MarketSerializer()
    class Meta:
        model = MarketSymbol
        fields = ['id', 'url', 'icon', 'name', 'base', 'quote', 'market', 'contract_type', 'volume']


class TagMetricsSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = TagMetrics
        fields = ['volume', 'market_cap', 'market_cap_change_24h']


class TagSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Tag
        fields = ['name', 'description', 'is_ecosystem', 'is_chain', 'is_portfolio', 'weight', 'best_symbols', 'metrics']

    metrics = TagMetricsSerializer()
    best_symbols = serializers.SerializerMethodField()

    def get_best_symbols(self, obj):
        return InlineGlobalSymbolSerializer(obj.symbols.all()[:3], many=True, context={'request': self.context['request']}).data


class InlineTagSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Tag
        fields = ['name', 'weight']


class InlineGlobalSymbolSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = GlobalSymbol
        fields = ['id', 'cid', 'display', 'base', 'image', 'markets']


class GlobalSymbolMetricsSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = GlobalSymbolMetrics
        fields = ['volume', 'market_cap', 'market_cap_change_24h', 'market_cap_change_percentage_24h', 'ath',
                  'ath_date', 'atl', 'atl_date', 'total_supply', 'circulating_supply', 'max_supply', 'ath_prox',
                  'atl_prox', 'ath_ratio', 'atl_ratio', 'data_updated', 'price_change_24h', 'price_change_percentage_24h',
                  'price_high_24h', 'price_low_24h', 'price', 'fully_diluted_valuation', 'market_cap_fdv_ratio', 'price_change_percentage_7d',
                  'price_change_percentage_7d', 'price_change_percentage_14d', 'price_change_percentage_30d', 'price_change_percentage_60d',
                  'price_change_percentage_200d', 'price_change_percentage_1y', ]


class GlobalSymbolSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = GlobalSymbol
        fields = ['cid', 'id', 'display', 'base', 'url', 'metrics', 'image', 'markets', 'symbols', 'description', 'homepage', 'cex_volume', 'tags',
                  'blockchain_site', 'whitepaper', 'official_forum_url', 'chat_url', 'announcement_url', 'twitter_screen_name', 'facebook_username', 
                  'subreddit_url', 'github_repo_url', 'genesis_date', 'sentiment_votes_up_percentage', 'sentiment_votes_down_percentage', 
                  'watchlist_portfolio_users', 'market_cap_rank', 'twitter_followers', 'developer_data', 'volume_distribution', 'bid_ask_spread_percentage_distribution',]
    tags = InlineTagSerializer(many=True)
    metrics = GlobalSymbolMetricsSerializer()
    symbols = InlineMarketSymbolSerializer(many=True)
    markets = serializers.SerializerMethodField()

    def get_markets(self, obj):
        return set(symbol.market.exchange_name for symbol in obj.symbols.all())


class StrategySerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Strategy
        fields = ['id', 'name', 'technical_name', 'code', 'version', 'description']


class SessionSerializer(serializers.HyperlinkedModelSerializer):
    symbol = MarketSymbolSerializer(required=False)
    market = serializers.CharField(source='account.market.exchange_name', required=False)
    account = MarketAccountSerializer(required=False)
    orders = serializers.HyperlinkedIdentityField(view_name='session-orders')
    signals = serializers.HyperlinkedIdentityField(view_name='session-signals')
    capital = serializers.FloatField(required=False)
    assets = serializers.FloatField(required=False)
    status = serializers.CharField(required=False)
    thread = serializers.SerializerMethodField()
    strategy = StrategySerializer(required=False)

    class Meta:
        model = Session
        fields = ['id', 'symbol', 'market', 'freq', 'group', 'started', 'ended', 
                  'strategy', 'status', 'last_price', 'last_kline_timestamp', 
                  'last_heartbeat', 'capital', 'assets', 'initial_capital', 
                  'initial_assets', 'buy_enabled', 'sell_enabled', 'account', 
                  'equity', 'orders', 'signals', 'health', 'url']

    def validate(self, data):
        instance = self.instance
        symbol = data.get('symbol', instance.symbol if instance else None)
        account = data.get('account', instance.account if instance else None)
        market = account.market if account else None
        if symbol and market:
            validate_symbol_against_market(symbol, market)
        return data


class DraftSessionSerializer(serializers.HyperlinkedModelSerializer):
    freq = serializers.ChoiceField(choices=Session.Freq.choices, default=Session.Freq.MIN15)
    symbol = serializers.PrimaryKeyRelatedField(queryset=MarketSymbol.objects.all())
    account = serializers.PrimaryKeyRelatedField(queryset=MarketAccount.objects.all())
    strategy = serializers.PrimaryKeyRelatedField(queryset=Strategy.objects.all())

    class Meta:
        model = Session
        fields = ['id', 'url', 'freq', 'symbol', 'account', 'strategy']

    def validate(self, attrs):
        data = super().validate(attrs)
        symbol = data['symbol']
        account = data['account']
        if symbol.market != account.market:
            raise serializers.ValidationError('Symbol and account must belong to the same market')
        if not symbol.spot_trading_enabled:
            raise serializers.ValidationError('Spot trading is not enabled for this symbol')
        if not account.credentials.active:
            raise serializers.ValidationError('Account is not active')
        return data


class SessionUpdateSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Session
        fields = ['id', 'url', 'capital', 'assets', 'buy_enabled', 'sell_enabled']


class SessionGroupSerializer(serializers.HyperlinkedModelSerializer):
    symbol = MarketSymbolSerializer()
    market = serializers.CharField(source='interface.market.exchange_name', allow_null=True)
    last_timestamp = serializers.DateTimeField(source='last_kline_dt')
    strategy = StrategySerializer()
    sessions = serializers.HyperlinkedIdentityField(view_name='sessiongroup-sessions')
    class Meta:
        model = SessionGroup
        fields = ['id', 'symbol', 'market', 'interface', 'freq', 'created_at', 'updated_at',
                  'started_at', 'stopped_at', 'strategy', 'status', 'last_price', 'last_timestamp',
                  'buy_enabled', 'sell_enabled', 'capital', 'assets', 'equity', 'source', 'sessions']


class OrderSerializer(serializers.HyperlinkedModelSerializer):
    symbol = InlineMarketSymbolSerializer()
    account = InlineMarketAccountSerializer()
    class Meta:
        model = Order
        fields = ['id', 'url', 'oid', 'deal_size', 'deal_funds', 'funds', 'price', 'order_type', 'market_timestamp',
                  'status', 'side', 'force', 'created_at', 'placed_at', 'symbol', 'account', 'session',
                  'group', 'messages']


class OrderPlacementSerializer(serializers.Serializer):
    account = serializers.PrimaryKeyRelatedField(queryset=MarketAccount.objects.all())
    symbol = serializers.PrimaryKeyRelatedField(queryset=MarketSymbol.objects.all())
    side = serializers.ChoiceField(choices=Order.Side.choices)
    deal_size = serializers.FloatField(required=False)
    funds = serializers.FloatField(required=False)

    def validate(self, data):
        super().validate(data)
        symbol = data['symbol']
        account = data['account']
        side = data['side']
        validate_order_payload(account, symbol, side, data.get('deal_size'), data.get('funds'))
        return data


class SessionOrderPlacementSerializer(serializers.Serializer):
    session = serializers.PrimaryKeyRelatedField(queryset=Session.objects.all())
    side = serializers.ChoiceField(choices=Order.Side.choices)
    deal_size = serializers.FloatField(required=False)
    funds = serializers.FloatField(required=False)

    def validate(self, attrs):
        super().validate(attrs)
        side = attrs['side']
        funds = attrs.get('funds')
        deal_size = attrs.get('deal_size')
        session = attrs['session']
        symbol = session.symbol
        account = session.account
        validate_order_payload(account, symbol, side, deal_size, funds, session)
        return attrs


class GroupOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupOrder
        fields = '__all__'


class SignalSerializer(serializers.HyperlinkedModelSerializer):
    symbol = InlineMarketSymbolSerializer()
    orders = serializers.HyperlinkedIdentityField(view_name='signal-orders')
    price = serializers.SerializerMethodField()

    def get_price(self, signal):
        # check for NaN
        return signal.price if signal.price == signal.price else None

    class Meta:
        model = Signal
        fields = ['id', 'url', 'session', 'group', 'symbol', 'timestamp', 'orders', 'side', 'price']


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = '__all__'


class ContactFormSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = ContactForm
        fields = ['name', 'email', 'message', 'user_agent']
