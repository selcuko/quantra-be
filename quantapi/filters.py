import django_filters as filters
from django.db.models import Q, Count
from .models import GlobalSymbol, MarketAccount, MarketSymbol, Session, SessionGroup, Tag


class MarketAccountFilter(filters.FilterSet):
    active = filters.BooleanFilter(field_name='credentials__active')
    internal = filters.BooleanFilter(field_name='credentials__internal')
    owner = filters.CharFilter(field_name='credentials__owner', lookup_expr='icontains')
    market = filters.CharFilter(method='filter_market')

    def filter_market(self, queryset, name, value):
        query = Q()
        for market in value.split(","):
            query |= Q(market__exchange_name__iexact=market)
        return queryset.filter(query)

    class Meta:
        model = MarketAccount
        fields = ['active', 'internal', 'owner']


class MarketSymbolFilter(filters.FilterSet):
    sort = filters.OrderingFilter(
        fields=(
            ('name', 'name'),
            ('market__exchange_name', 'market'),
            ('symbol__market_cap', 'market_cap'),
        ))
    market = filters.CharFilter(field_name='market__exchange_name', lookup_expr='iexact')
    name = filters.CharFilter(field_name='name', lookup_expr='startswith')
    base = filters.CharFilter(field_name='base', lookup_expr='startswith')
    quote = filters.CharFilter(field_name='quote', lookup_expr='iexact')
    spot_enabled = filters.BooleanFilter(field_name='spot_trading_enabled')
    contract_type = filters.CharFilter(field_name='contract_type', lookup_expr='iexact')

    class Meta:
        model = MarketSymbol
        fields = ['market', 'name', 'base', 'quote', 'sort', 'spot_enabled', 'contract_type']


class SessionFilter(filters.FilterSet):
    status = filters.CharFilter(method='filter_status')
    source = filters.MultipleChoiceFilter(choices=Session.CandleSource.choices, field_name='candle_source')
    account = filters.CharFilter(field_name='account__credentials__owner', label='account owner', lookup_expr='icontains')
    strategy = filters.CharFilter(field_name='strategy__pk', label='strategy')
    market = filters.CharFilter(field_name='account__market__exchange_name', lookup_expr='iexact', label='market ID')
    symbol = filters.CharFilter(field_name='symbol__base', label='symbol ID')
    created_after = filters.DateTimeFilter(field_name='started', lookup_expr='gte')

    class Meta:
        model = Session
        fields = ['status', 'source', 'strategy', 'market', 'account', 'symbol', 'created_after']

    def filter_status(self, queryset, name, value):
        query = Q()
        for status in value.split(","):
            query |= Q(status=status)
        return queryset.filter(query)


class SessionGroupFilter(filters.FilterSet):
    status = filters.MultipleChoiceFilter(choices=SessionGroup.Status.choices)
    source = filters.MultipleChoiceFilter(choices=Session.CandleSource.choices, field_name='candle_source')

    class Meta:
        model = SessionGroup
        fields = ['status']


class GlobalSymbolFilter(filters.FilterSet):
    sort = filters.OrderingFilter(
        fields=(
            ('market_cap', 'market_cap'),
            ('volume', 'volume'),
            ('price_change_percentage_24h', 'price_change_percentage_24h'),
            ('supply_ratio', 'supply_ratio'),
            ('ath', 'ath'),
            ('ath_date', 'ath_date'),
            ('ath_prox', 'ath_prox'),
            ('ath_ratio', 'ath_ratio'),
            ('atl', 'atl'),
            ('atl_date', 'atl_date'),
            ('atl_prox', 'atl_prox'),
            ('atl_ratio', 'atl_ratio'),
            ('volume24h_to_mcap', 'volume24h_to_mcap'),
        )
    )
    contract_type = filters.CharFilter(field_name='contract_type', lookup_expr='iexact')
    name = filters.CharFilter(field_name='name', lookup_expr='icontains')
    base = filters.CharFilter(field_name='base', lookup_expr='icontains')
    quote = filters.CharFilter(field_name='quote', lookup_expr='iexact')
    tags = filters.CharFilter(method='filter_tags')
    market = filters.CharFilter(method='filter_market')
    is_favorite = filters.BooleanFilter(field_name='favorite')
    is_stablecoin = filters.BooleanFilter(field_name='is_stablecoin')
    ath__gte = filters.NumberFilter(field_name='ath', lookup_expr='gte')
    ath__lte = filters.NumberFilter(field_name='ath', lookup_expr='lte')
    atl__gte = filters.NumberFilter(field_name='atl', lookup_expr='gte')
    atl__lte = filters.NumberFilter(field_name='atl', lookup_expr='lte')
    ath_date__gte = filters.DateFilter(field_name='ath_date', lookup_expr='gte')
    ath_date__lte = filters.DateFilter(field_name='ath_date', lookup_expr='lte')
    atl_date__gte = filters.DateFilter(field_name='atl_date', lookup_expr='gte')
    atl_date__lte = filters.DateFilter(field_name='atl_date', lookup_expr='lte')
    ath_prox__gte = filters.NumberFilter(field_name='ath_prox', lookup_expr='gte')
    ath_prox__lte = filters.NumberFilter(field_name='ath_prox', lookup_expr='lte')
    atl_prox__gte = filters.NumberFilter(field_name='atl_prox', lookup_expr='gte')
    atl_prox__lte = filters.NumberFilter(field_name='atl_prox', lookup_expr='lte')
    ath_ratio__gte = filters.NumberFilter(field_name='ath_ratio', lookup_expr='gte')
    ath_ratio__lte = filters.NumberFilter(field_name='ath_ratio', lookup_expr='lte')
    atl_ratio__gte = filters.NumberFilter(field_name='atl_ratio', lookup_expr='gte')
    atl_ratio__lte = filters.NumberFilter(field_name='atl_ratio', lookup_expr='lte')
    supply_ratio__gte = filters.NumberFilter(field_name='supply_ratio', lookup_expr='gte')
    supply_ratio__lte = filters.NumberFilter(field_name='supply_ratio', lookup_expr='lte')
    volume__gte = filters.NumberFilter(field_name='volume', lookup_expr='gte')
    volume__lte = filters.NumberFilter(field_name='volume', lookup_expr='lte')
    market_cap__gte = filters.NumberFilter(field_name='market_cap', lookup_expr='gte')
    market_cap__lte = filters.NumberFilter(field_name='market_cap', lookup_expr='lte')
    price_change__gte = filters.NumberFilter(field_name='price_change_percentage_24h', lookup_expr='gte')
    price_change__lte = filters.NumberFilter(field_name='price_change_percentage_24h', lookup_expr='lte')
    price_change_percentage_24h__gte = filters.NumberFilter(field_name='price_change_percentage_24h', lookup_expr='gte')
    price_change_percentage_24h__lte = filters.NumberFilter(field_name='price_change_percentage_24h', lookup_expr='lte')
    volume24h_to_mcap__gte = filters.NumberFilter(field_name='volume24h_to_mcap', lookup_expr='gte')
    volume24h_to_mcap__lte = filters.NumberFilter(field_name='volume24h_to_mcap', lookup_expr='lte')

    def filter_market(self, queryset, name, value):
        query = Q()
        if value.lower() == 'notnull':
            return queryset.exclude(available_markets='[]')
        for market in value.split(","):
            query &= Q(available_markets__icontains=market)
        return queryset.filter(query)

    def filter_tags(self, queryset, name, value):
        query = Q()
        for tag in value.split(","):
            query &= Q(tags_flat__icontains=tag)
        return queryset.filter(query)

    class Meta:
        model = GlobalSymbol
        fields = ['market', 'name', 'base', 'quote', 'supply_ratio', 'sort', 'contract_type', 'tags', 'is_favorite']


class TagFilter(filters.FilterSet):
    class Meta:
        model = Tag
        fields = ['symbols', 'name']

    symbols = filters.CharFilter(method='filter_symbols')
    name = filters.CharFilter(field_name='name', lookup_expr='icontains')

    def filter_symbols(self, queryset, name, value):
        cids = value.split(",")
        return queryset.filter(symbols__cid__in=cids).annotate(symbol_count=Count('symbols')).filter(symbol_count=len(cids)).distinct()
