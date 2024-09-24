from django.test import tag
import django_filters as filters
from django.db.models import Q, Count, Aggregate
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
            ('symbol__metrics__volume', 'volume'),
        ))
    market = filters.CharFilter(field_name='market__exchange_name', lookup_expr='iexact')
    name = filters.CharFilter(field_name='name', lookup_expr='istartswith')
    base = filters.CharFilter(field_name='base', lookup_expr='iexact')
    quote = filters.CharFilter(field_name='quote', lookup_expr='iexact')
    spot_enabled = filters.BooleanFilter(field_name='spot_trading_enabled')
    contract_type = filters.CharFilter(field_name='contract_type', lookup_expr='iexact')
    volume = filters.RangeFilter(field_name='symbol__metrics__volume')

    class Meta:
        model = MarketSymbol
        fields = ['market', 'name', 'base', 'quote', 'sort', 'spot_enabled', 'contract_type', 'volume']


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
    contract_type = filters.CharFilter(field_name='contract_type', lookup_expr='iexact')
    name = filters.CharFilter(field_name='name', lookup_expr='icontains')
    base = filters.CharFilter(field_name='base', lookup_expr='iexact')
    quote = filters.CharFilter(field_name='quote', lookup_expr='iexact')
    tags = filters.CharFilter(method='filter_tags')
    market = filters.CharFilter(method='filter_market')
    is_favorite = filters.BooleanFilter(field_name='favorite')
    is_stablecoin = filters.BooleanFilter(field_name='is_stablecoin')
    volume = filters.RangeFilter(field_name='metrics__volume')

    ordering = filters.OrderingFilter(
        fields=(
            ('name', 'name'),
            ('base', 'base'),
            ('quote', 'quote'),
            ('metrics__market_cap', 'market_cap'),
            ('metrics__volume', 'volume'),
        )
    )

    def filter_market(self, queryset, name, value):
        if value.lower() == 'notnull':
            return queryset.filter(symbols__isnull=False).distinct()
        market_list = value.split(",")
        return queryset\
            .filter(symbols__market__exchange_name__in=market_list, symbols__contract_type='SPOT')\
            .annotate(market_count=Count('symbols__market', distinct=True))\
            .filter(market_count=len(market_list))\
            .distinct()

    def filter_tags(self, queryset, name, value):
        tag_list = value.split(",")
        return queryset\
            .filter(tags__name__in=tag_list)\
            .annotate(tag_count=Count('tags', distinct=True))\
            .filter(tag_count=len(tag_list))\
            .distinct()

    class Meta:
        model = GlobalSymbol
        fields = ['market', 'name', 'base', 'quote', 'contract_type', 'tags', 'is_favorite', 'cid', 'volume', 'ordering']


class TagFilter(filters.FilterSet):
    class Meta:
        model = Tag
        fields = ['symbols', 'name', 'volume']

    symbols = filters.CharFilter(method='filter_symbols')
    name = filters.CharFilter(field_name='name', lookup_expr='icontains')
    volume = filters.NumericRangeFilter(field_name='metrics__volume')

    def filter_symbols(self, queryset, name, value):
        cids = value.split(",")
        return queryset.filter(symbols__cid__in=cids).annotate(symbol_count=Count('symbols')).filter(symbol_count=len(cids)).distinct()
