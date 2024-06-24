import django_filters as filters
from .models import MarketAccount, MarketSymbol, Session, SessionGroup


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

    class Meta:
        model = Session
        fields = ['status', 'source']


class SessionGroupFilter(filters.FilterSet):
    status = filters.MultipleChoiceFilter(choices=SessionGroup.Status.choices)
    source = filters.MultipleChoiceFilter(choices=Session.CandleSource.choices, field_name='candle_source')

    class Meta:
        model = SessionGroup
        fields = ['status']
