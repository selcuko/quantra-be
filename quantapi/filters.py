import django_filters as filters
from django.db.models import Q
from .models import GlobalSymbol, MarketAccount, MarketSymbol, Session, SessionGroup


class MarketAccountFilter(filters.FilterSet):
    active = filters.BooleanFilter(field_name='credentials__active')
    internal = filters.BooleanFilter(field_name='credentials__internal')

    class Meta:
        model = MarketAccount
        fields = ['active', 'internal']


class MarketSymbolFilter(filters.FilterSet):
    market = filters.CharFilter(field_name='market__exchange_name', lookup_expr='iexact')
    name = filters.CharFilter(field_name='name', lookup_expr='icontains')
    base = filters.CharFilter(field_name='base', lookup_expr='iexact')
    quote = filters.CharFilter(field_name='quote', lookup_expr='iexact')
    spot_enabled = filters.BooleanFilter(field_name='spot_trading_enabled')

    class Meta:
        model = MarketSymbol
        fields = ['market', 'name', 'base', 'quote']


class SessionFilter(filters.FilterSet):
    status = filters.MultipleChoiceFilter(choices=Session.Status.choices)
    source = filters.MultipleChoiceFilter(choices=Session.CandleSource.choices, field_name='candle_source')
    strategy = filters.CharFilter(field_name='strategy__pk', label='strategy')
    market = filters.CharFilter(field_name='market_account__market__pk', lookup_expr='iexact', label='market ID')
    market_name = filters.CharFilter(field_name='market_account__market__exchange_name', lookup_expr='icontains', label='market name')
    account = filters.CharFilter(field_name='account__pk', label='account ID')
    symbol = filters.CharFilter(field_name='symbol__pk', label='symbol ID')
    symbol_name = filters.CharFilter(field_name='symbol__name', lookup_expr='icontains', label='symbol name')

    class Meta:
        model = Session
        fields = ['status', 'source', 'strategy', 'market', 'account']


class SessionGroupFilter(filters.FilterSet):
    status = filters.MultipleChoiceFilter(choices=SessionGroup.Status.choices)
    source = filters.MultipleChoiceFilter(choices=Session.CandleSource.choices, field_name='candle_source')

    class Meta:
        model = SessionGroup
        fields = ['status']


class GlobalSymbolFilter(filters.FilterSet):
    name = filters.CharFilter(field_name='name', lookup_expr='icontains')
    category = filters.CharFilter(method='filter_category')
    market = filters.CharFilter(method='filter_market')
    is_favorite = filters.BooleanFilter(field_name='favorite')
    is_stablecoin = filters.BooleanFilter(field_name='stablecoin')
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
    volume24h_to_mcap__gte = filters.NumberFilter(field_name='volume24h_to_market_cap', lookup_expr='gte')
    volume24h_to_mcap__lte = filters.NumberFilter(field_name='volume24h_to_market_cap', lookup_expr='lte')

    def filter_market(self, queryset, name, value):
        query = Q()
        for market in value.split(","):
            query &= Q(available_markets__icontains=market)
        return queryset.filter(query)

    def filter_category(self, queryset, name, value):
        query = Q()
        for tag in value.split(","):
            query &= Q(tags_flat__icontains=tag)
        return queryset.filter(query)

    class Meta:
        model = GlobalSymbol
        fields = ['market', 'name', 'base', 'quote', 'supply_ratio']
