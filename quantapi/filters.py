import django_filters as filters
from .models import MarketAccount, Session, SessionGroup


class MarketAccountFilter(filters.FilterSet):
    active = filters.BooleanFilter(field_name='credentials__active')
    internal = filters.BooleanFilter(field_name='credentials__internal')

    class Meta:
        model = MarketAccount
        fields = ['active', 'internal']


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
