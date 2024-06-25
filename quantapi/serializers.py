import json
from rest_framework import serializers
from rest_framework.response import Response
from quantapi.models import Endpoint, GlobalSymbol, GroupOrder, Market, MarketAccount, MarketSymbol, Notification, Order, Session, SessionGroup, Signal, Strategy, Subscription
from quantapi.validations import validate_symbol_against_market


class MarketSerializer(serializers.HyperlinkedModelSerializer):
    prices = serializers.HyperlinkedIdentityField(view_name='market-prices')

    class Meta:
        model = Market
        fields = ['id', 'exchange_name', 'prices_updated', 'prices']


class MarketAccountSerializer(serializers.HyperlinkedModelSerializer):
    assets = serializers.SerializerMethodField()
    market = serializers.CharField(source='market.exchange_name')
    owner = serializers.CharField(source='credentials.owner')
    active = serializers.BooleanField(source='credentials.active')
    internal = serializers.BooleanField(source='credentials.internal')
    prices_updated = serializers.DateTimeField(source='market.prices_updated', allow_null=True)

    class Meta:
        model = MarketAccount
        fields = ['id', 'market', 'equity', 'capital', 'assets', 'last_cache', 
                  'owner', 'active', 'internal', 'prices_updated']

    def get_assets(self, obj):
        # XXX: this serializer method is hacky. come back here to optimize.
        assets = json.loads(obj.assets or '{}')
        prices = json.loads(obj.market.prices or '{}')
        payload = {}
        for k, v in assets.items():
            price = prices.get(f'{k}-USDT', 0)
            if k == 'USDT' or v <= 0:
                continue
            try:
                ms = MarketSymbol.objects.get(market=obj.market, base=k, symbol__isnull=False)
            except MarketSymbol.DoesNotExist:
                ms = None
            payload[k] = {
                'amount': v,
                'price': price,
                'value': (v * price) or None,
                'icon': ms.symbol.image if ms and ms.symbol else None
            }
        return payload


class MarketSymbolSerializer(serializers.HyperlinkedModelSerializer):
    market = serializers.CharField(source='market.exchange_name')
    icon = serializers.URLField(source='symbol.image', allow_null=True)
    price = serializers.SerializerMethodField()
    price_updated = serializers.DateTimeField(source='market.prices_updated', allow_null=True)
    class Meta:
        model = MarketSymbol
        fields = ['symbol', 'market', 'name', 'base', 'quote', 'base_precision', 'quote_precision', 
                  'spot_trading_enabled', 'icon', 'price', 'price_updated', 'id']

    def get_price(self, obj):
        prices = json.loads(obj.market.prices or '{}')
        return prices.get(obj.name)


class GlobalSymbolSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = GlobalSymbol
        fields = ['id', 'cid', 'name', 'display', 'base', 'quote', 'tags', 'symbols', 'data_source', 
                  'is_stablecoin', 'ath', 'atl', 'ath_date', 'atl_date', 'volume', 'market_cap', 
                  'circulating_supply', 'max_supply', 'total_supply', 'last_updated', 'price', 
                  'supply_ratio', 'ath_prox', 'atl_prox', 'volume24h_to_mcap', 'image']
    tags = serializers.StringRelatedField(many=True)
    symbols = serializers.HyperlinkedRelatedField(many=True, read_only=True, view_name='marketsymbol-detail')


class StrategySerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Strategy
        fields = ['id', 'name', 'technical_name', 'code', 'version', 'description']


class SessionSerializer(serializers.HyperlinkedModelSerializer):
    symbol = MarketSymbolSerializer(required=False)
    symbol_id = serializers.PrimaryKeyRelatedField(queryset=MarketSymbol.objects.all(), source='symbol', write_only=True)
    market = serializers.CharField(source='account.market.exchange_name', required=False)
    account = MarketAccountSerializer(required=False)
    account_id = serializers.PrimaryKeyRelatedField(queryset=MarketAccount.objects.all(), source='account', write_only=True)
    orders = serializers.HyperlinkedIdentityField(view_name='session-orders')
    signals = serializers.HyperlinkedIdentityField(view_name='session-signals')
    capital = serializers.FloatField(required=False)
    assets = serializers.FloatField(required=False)
    status = serializers.CharField(required=False)
    thread = serializers.SerializerMethodField()
    strategy = StrategySerializer(required=False)
    strategy_id = serializers.PrimaryKeyRelatedField(queryset=Strategy.objects.all(), source='strategy', write_only=True)

    class Meta:
        model = Session
        fields = ['id', 'symbol', 'market', 'freq', 'group', 'started', 'ended', 
                  'strategy', 'strategy_id', 'status', 'last_price', 'last_kline_timestamp', 
                  'last_heartbeat', 'capital', 'assets', 'initial_capital', 
                  'initial_assets', 'buy_enabled', 'sell_enabled', 'account', 
                  'equity', 'orders', 'signals', 'account_id', 'symbol_id', 'thread', 'health']

    def get_thread(self, obj):
        if not obj.thread:
            return {}
        return {
            'ident': obj.thread.ident,
            'is_alive': obj.thread.is_alive(),
            'name': obj.thread.name
        }

    def validate(self, data):
        symbol = data.get('symbol')
        account = data.get('account')
        market = account.market
        validate_symbol_against_market(symbol, market)
        return data


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


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = '__all__'


class GroupOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupOrder
        fields = '__all__'


class SignalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Signal
        fields = '__all__'


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = '__all__'


class EndpointSerializer(serializers.ModelSerializer):
    class Meta:
        model = Endpoint
        fields = '__all__'


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'


class IssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'


class ThreadSerializer(serializers.Serializer):
    ident = serializers.CharField()
    is_alive = serializers.BooleanField()
    name = serializers.CharField()
    source = serializers.SerializerMethodField()

    def get_source(self, obj):
        if obj.name.startswith('LiveLoop-'):
            return 'LiveLoop'
        if obj.name.startswith('LoopGroup-'):
            return 'LoopGroup'
        return None


class LiveLoopSerializer(serializers.Serializer):
    symbol = serializers.CharField()
    market = serializers.CharField()
    account = MarketAccountSerializer()
    #group = serializers.IntegerField()
    session = serializers.IntegerField(source='session.pk')
    thread = ThreadSerializer()


class LoopGroupSerializer(serializers.Serializer):
    symbol = serializers.CharField()
    market = serializers.CharField()
    account = MarketAccountSerializer()
    group = serializers.HyperlinkedRelatedField(view_name='sessiongroup-detail', read_only=True)
    session = serializers.HyperlinkedRelatedField(view_name='session-detail', read_only=True)
    thread = ThreadSerializer()
