import json
from rest_framework import serializers
from quantapi.models import Endpoint, GlobalSymbol, GroupOrder, Market, MarketAccount, MarketSymbol, Notification, Order, Session, SessionGroup, Signal, Strategy, Subscription


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

    class Meta:
        model = MarketAccount
        fields = ['id', 'market', 'equity', 'capital', 'assets', 'last_cache', 
                  'owner', 'active', 'internal']

    def get_assets(self, obj):
        assets = json.loads(obj.assets or '{}')
        return {k: v for k, v in assets.items() if v > 0}


class MarketSymbolSerializer(serializers.HyperlinkedModelSerializer):
    market = serializers.CharField(source='market.exchange_name')
    class Meta:
        model = MarketSymbol
        fields = ['symbol', 'market', 'name', 'base', 'quote', 'base_precision', 'quote_precision', 'spot_trading_enabled']


class GlobalSymbolSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = GlobalSymbol
        fields = ['id', 'cid', 'name', 'display', 'base', 'quote', 'tags', 'symbols', 'data_source', 'is_stablecoin', 'ath', 'atl', 'ath_date', 'atl_date', 'volume', 'market_cap', 'circulating_supply', 'max_supply', 'total_supply', 'last_updated', 'price', 'supply_ratio', 'ath_prox', 'atl_prox', 'volume24h_to_mcap']
    tags = serializers.StringRelatedField(many=True)
    symbols = serializers.HyperlinkedRelatedField(many=True, read_only=True, view_name='marketsymbol-detail')


class StrategySerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Strategy
        fields = '__all__'


class SessionSerializer(serializers.HyperlinkedModelSerializer):
    symbol = serializers.CharField(source='symbol.name')
    market = serializers.CharField(source='account.market.exchange_name')
    account = MarketAccountSerializer()
    orders = serializers.HyperlinkedIdentityField(view_name='session-orders')
    signals = serializers.HyperlinkedIdentityField(view_name='session-signals')

    class Meta:
        model = Session
        fields = ['id', 'symbol', 'market', 'freq', 'group', 'started', 'ended', 
                  'strategy', 'status', 'last_price', 'last_kline_timestamp', 
                  'last_heartbeat', 'capital', 'assets', 'initial_capital', 
                  'initial_assets', 'buy_enabled', 'sell_enabled', 'account', 
                  'equity', 'orders', 'signals']


class SessionGroupSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = SessionGroup
        fields = '__all__'


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
