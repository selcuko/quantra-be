import json
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from liveloop import LiveLoop
from quantapi.models import Endpoint, GlobalSymbol, GroupOrder, Issue, Market, MarketAccount, MarketSymbol, Notification, Order, Session, SessionGroup, Signal, Strategy, Subscription
from quantapi.serializers import (EndpointSerializer, GlobalSymbolSerializer, GroupOrderSerializer, IssueSerializer, MarketAccountSerializer, MarketSerializer, MarketSymbolSerializer, NotificationSerializer, OrderSerializer,
                                  SessionGroupSerializer, SessionSerializer, SignalSerializer, StrategySerializer, SubscriptionSerializer)
from quantapi.filters import MarketSymbolFilter, SessionFilter, MarketAccountFilter, SessionGroupFilter


class MarketViewSet(viewsets.ModelViewSet):
    queryset = Market.objects.all()
    serializer_class = MarketSerializer

    @action(detail=True, methods=['get'])
    def prices(self, request, pk=None):
        market = self.get_object()
        prices = json.loads(market.prices or '{}')
        return Response(prices)


class MarketAccountViewSet(viewsets.ModelViewSet):
    queryset = MarketAccount.objects.all()
    serializer_class = MarketAccountSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = MarketAccountFilter


class MarketSymbolViewSet(viewsets.ModelViewSet):
    queryset = MarketSymbol.objects.all()
    serializer_class = MarketSymbolSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = MarketSymbolFilter

    def get_queryset(self):
        return MarketSymbol.objects.select_related('market', 'symbol').all()

    @action(detail=False, methods=['get'], url_path='(?P<market>[^/.]+)', url_name='market')
    def market(self, request, market):
        """Return all symbols for a given market."""
        symbols = MarketSymbol.objects.filter(market__exchange_name=market.upper())
        serializer = MarketSymbolSerializer(symbols, many=True, context={'request': request})
        return Response(serializer.data)


class GlobalSymbolViewSet(viewsets.ModelViewSet):
    queryset = GlobalSymbol.objects.all()
    serializer_class = GlobalSymbolSerializer

    def get_queryset(self):
        return GlobalSymbol.objects.prefetch_related('tags', 'symbols').all()


class StrategyViewSet(viewsets.ModelViewSet):
    queryset = Strategy.objects.all()
    serializer_class = StrategySerializer


class SessionViewSet(viewsets.ModelViewSet):
    queryset = Session.objects.all()
    serializer_class = SessionSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = SessionFilter

    def get_queryset(self):
        return Session.objects.select_related('symbol', 'account').all()

    @action(detail=True, methods=['get'])
    def orders(self, request, pk=None):
        session = self.get_object()
        orders = session.orders.all()
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def signals(self, request, pk=None):
        session = self.get_object()
        signals = session.signals.all()
        serializer = SignalSerializer(signals, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        session = self.get_object()
        if session.status != Session.Status.PLANNED:
            return Response({'detail': 'Session must be in PLANNED state to start.'}, status=400)
        ll = LiveLoop.from_session(session)
        ll.run()
        return Response({'detail': 'Session will start in a few seconds.'})


class SessionGroupViewSet(viewsets.ModelViewSet):
    queryset = SessionGroup.objects.all()
    serializer_class = SessionGroupSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = SessionGroupFilter

    def get_queryset(self):
        return SessionGroup.objects.select_related('symbol', 'interface').all()


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    filter_backends = [DjangoFilterBackend]


class GroupOrderViewSet(viewsets.ModelViewSet):
    queryset = GroupOrder.objects.all()
    serializer_class = GroupOrderSerializer
    filter_backends = [DjangoFilterBackend]


class SignalViewSet(viewsets.ModelViewSet):
    queryset = Signal.objects.all()
    serializer_class = SignalSerializer
    filter_backends = [DjangoFilterBackend]


class SubscriptionViewSet(viewsets.ModelViewSet):
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer
    filter_backends = [DjangoFilterBackend]


class EndpointViewSet(viewsets.ModelViewSet):
    queryset = Endpoint.objects.all()
    serializer_class = EndpointSerializer
    filter_backends = [DjangoFilterBackend]


class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    filter_backends = [DjangoFilterBackend]


class IssueViewSet(viewsets.ModelViewSet):
    queryset = Issue.objects.all()
    serializer_class = IssueSerializer
    filter_backends = [DjangoFilterBackend]
