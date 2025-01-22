import json
from rest_framework import serializers
from quantapi.models import (ContactForm, GlobalSymbol, Market, MarketAccount, MarketCredentials, 
                             MarketSymbol, Tag)
from quantapi.validations import validate_symbol_against_market


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
    #price = serializers.SerializerMethodField()
    price_updated = serializers.DateTimeField(source='market.prices_updated', allow_null=True)
    cid = serializers.CharField(source='symbol.cid', allow_null=True)
    available_contracts = serializers.SerializerMethodField()
    class Meta:
        model = MarketSymbol
        fields = ['symbol', 'market', 'exchange_name', 'name', 'base', 'quote', 'base_precision', 'quote_precision', 
                  'spot_trading_enabled', 'icon', 'price_updated', 'id', 'url', 'cid', 'contract_type', 'available_contracts', 'volume']

    def get_price(self, obj):
        prices = json.loads(obj.market.prices or '{}')
        return prices.get(obj.name)
    
    def get_available_contracts(self, obj):
        return obj.available_contracts.split(',') if obj.available_contracts else []


class InlineMarketSymbolSerializer(serializers.HyperlinkedModelSerializer):
    icon = serializers.URLField(source='symbol.image', allow_null=True)
    market = MarketSerializer()
    class Meta:
        model = MarketSymbol
        fields = ['id', 'url', 'icon', 'name', 'base', 'quote', 'market', 'contract_type', 'volume']


class TagSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Tag
        fields = ['name', 'display', 'description', 'is_ecosystem', 'is_chain', 'is_portfolio', 'weight', 'best_symbols', 'volume', 'market_cap', 'market_cap_change_24h']

    best_symbols = serializers.SerializerMethodField()

    def get_best_symbols(self, obj):
        return InlineGlobalSymbolSerializer(obj.top_symbols, many=True, context={'request': self.context['request']}).data


class InlineTagSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Tag
        fields = ['name', 'weight', 'is_portfolio', 'is_chain', 'is_ecosystem', 'display']


class InlineGlobalSymbolSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = GlobalSymbol
        fields = ['id', 'cid', 'display', 'base', 'image', 'markets']


class GlobalSymbolSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = GlobalSymbol
        fields = ['cid', 'id', 'display', 'base', 'url', 'image', 'markets', 'symbols', 'description', 'homepage', 'cex_volume', 'tags',
                  'blockchain_site', 'whitepaper', 'official_forum_url', 'chat_url', 'announcement_url', 'twitter_screen_name', 'facebook_username', 
                  'subreddit_url', 'github_repo_url', 'genesis_date', 'sentiment_votes_up_percentage', 'sentiment_votes_down_percentage', 
                  'watchlist_portfolio_users', 'market_cap_rank', 'twitter_followers', 'developer_data', 'volume_distribution', 'bid_ask_spread_percentage_distribution',
                  'volume', 'market_cap', 'market_cap_change_24h', 'market_cap_change_percentage_24h', 'ath',
                  'ath_date', 'atl', 'atl_date', 'total_supply', 'circulating_supply', 'max_supply', 'ath_prox',
                  'atl_prox', 'ath_ratio', 'atl_ratio', 'data_updated', 'price_change_24h', 'price_change_percentage_24h',
                  'price_high_24h', 'price_low_24h', 'price', 'fully_diluted_valuation', 'market_cap_fdv_ratio', 'price_change_percentage_7d',
                  'price_change_percentage_7d', 'price_change_percentage_14d', 'price_change_percentage_30d', 'price_change_percentage_60d',
                  'price_change_percentage_200d', 'price_change_percentage_1y', 'volume24h_to_mcap', 'circulating_percent']
    tags = InlineTagSerializer(many=True)
    symbols = InlineMarketSymbolSerializer(many=True)
    markets = serializers.SerializerMethodField()

    def get_markets(self, obj):
        return set(symbol.market.exchange_name for symbol in obj.symbols.all())


class ContactFormSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = ContactForm
        fields = ['name', 'email', 'message', 'user_agent']
