import json
import threading
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from cache import LIVELOOPS, LOOPGROUPS
from liveloop import LiveLoop
from quantapi.models import (Endpoint, GlobalSymbol, GroupOrder, Issue, Market, MarketAccount, MarketSymbol, 
                             Notification, Order, Session, SessionGroup, Signal, Strategy, Subscription)
from quantapi.serializers import (EndpointSerializer, GlobalSymbolSerializer, GroupOrderSerializer, IssueSerializer, 
                                  LiveLoopSerializer, LoopGroupSerializer, MarketAccountSerializer, MarketSerializer, 
                                  MarketSymbolSerializer, NotificationSerializer, OrderSerializer, SessionGroupSerializer, 
                                  SessionSerializer, SignalSerializer, StrategySerializer, SubscriptionSerializer, ThreadSerializer)
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
        session.status = Session.Status.ONGOING
        session.save()
        return Response({'detail': 'Session will start in a few seconds.'})

    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        session = self.get_object()
        if session.status != Session.Status.ONGOING:
            return Response({'detail': 'Session must be in ONGOING state to pause.'}, status=400)
        ll = LIVELOOPS.get(session.id)
        if not ll:
            return Response({'detail': 'Session not found in the cache.'}, status=503)
        ll.stop()
        session.status = Session.Status.PAUSED
        session.save()
        return Response({'detail': 'Session will pause in a few seconds.'})

    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        force = request.data.get('force', False)
        session = self.get_object()
        if not force and session.status != Session.Status.PAUSED:
            return Response({'detail': 'Session must be in PAUSED state to resume.'}, status=400)
        ll = LiveLoop.from_session(session)
        ll.run()
        session.status = Session.Status.ONGOING
        session.save()
        return Response({'detail': 'Session will resume in a few seconds.'})

    @action(detail=True, methods=['post'])
    def terminate(self, request, pk=None):
        session = self.get_object()
        if session.status not in [Session.Status.ONGOING, Session.Status.PAUSED]:
            return Response({'detail': 'Session must be in ONGOING or PAUSED state to terminate.'}, status=400)
        ll = LIVELOOPS.get(session.id)
        if not ll:
            return Response({'detail': 'Session not found in the cache.'}, status=503)
        ll.stop()
        session.status = Session.Status.TERMINATED
        session.save()
        return Response({'detail': 'Session will terminate in a few seconds.'})

class SessionGroupViewSet(viewsets.ModelViewSet):
    queryset = SessionGroup.objects.all()
    serializer_class = SessionGroupSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = SessionGroupFilter

    def get_queryset(self):
        return SessionGroup.objects.select_related('symbol', 'interface').all()

    @action(detail=True, methods=['get'])
    def sessions(self, request, pk=None):
        group = self.get_object()
        sessions = group.sessions.all()
        serializer = SessionSerializer(sessions, many=True, context={'request': request})
        return Response(serializer.data)


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


class LiveLoopViewSet(viewsets.ViewSet):
    def list(self, request):
        return Response(LiveLoopSerializer(LIVELOOPS.values(), many=True).data)


class LoopGroupViewSet(viewsets.ViewSet):
    def list(self, request):
        return Response(LoopGroupSerializer(LOOPGROUPS.values(), many=True).data)


class HealthViewSet(viewsets.ViewSet):
    def list(self, request):
        return Response({'status': 'ok'})


class ThreadViewSet(viewsets.ViewSet):
    def list(self, request):
        threads = threading.enumerate()
        serializer = ThreadSerializer(threads, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk):
        try:
            thread = next(t for t in threading.enumerate() if t.ident == int(pk))
        except StopIteration:
            return Response({'detail': 'Thread not found, ensure it\'s an alive thread.'}, status=404)
        serializer = ThreadSerializer(thread)
        return Response(serializer.data)
