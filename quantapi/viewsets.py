import json
import threading

from django.db.models import Prefetch, Count, Q
from django_filters.rest_framework import DjangoFilterBackend
from pytest import mark
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.response import Response

from cache import LIVELOOPS, LOOPGROUPS
from loops import LiveLoop
from markets.errors import OrderPlacementError
from order import OrderManager
from quantapi.filters import (GlobalSymbolFilter, MarketAccountFilter, MarketSymbolFilter,
                              SessionFilter, SessionGroupFilter)
from quantapi.models import (ContactForm, GlobalSymbol, GroupOrder, Market,
                             MarketAccount, MarketSymbol, Order,
                             Session, SessionGroup, Signal, Strategy,
                             Subscription, Tag)
from quantapi.serializers import (ContactFormSerializer, DraftSessionSerializer,
                                  GlobalSymbolSerializer, GroupOrderSerializer,
                                  LiveLoopSerializer,
                                  LoopGroupSerializer, MarketAccountSerializer,
                                  MarketSerializer, MarketSymbolSerializer, NewAccountSerializer,
                                  OrderPlacementSerializer, OrderSerializer,
                                  SessionGroupSerializer,
                                  SessionOrderPlacementSerializer,
                                  SessionSerializer, SessionUpdateSerializer,
                                  SignalSerializer, StrategySerializer,
                                  SubscriptionSerializer, TagSerializer, ThreadSerializer)
from quantapi.validations import validate_session_can_start


class MarketViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Market.objects.all()
    serializer_class = MarketSerializer

    @action(detail=True, methods=['get'])
    def prices(self, request, pk):
        market = self.get_object()
        prices = json.loads(market.prices or '{}')
        return Response(prices)

    @action(detail=True, methods=['get'])
    def fields(self, request, pk):
        market: Market = self.get_object()
        fields = market.fields()
        return Response(fields)

    def get_queryset(self):
        return Market.objects.annotate(
            tradable_symbols_count=Count('symbols', filter=Q(symbols__spot_trading_enabled=True))
        ).prefetch_related('symbols', 'accounts')


class MarketAccountViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MarketAccount.objects.all()
    serializer_class = MarketAccountSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = MarketAccountFilter

    def get_queryset(self):
        return MarketAccount.objects.select_related(
            'market', 'credentials'
        ).prefetch_related(
            Prefetch(
                'market__symbols', 
                queryset=MarketSymbol.objects.select_related('symbol')
            )
        )

    @action(detail=True, methods=['get', 'post'])
    def refresh(self, request, pk):
        account: MarketAccount = self.get_object()
        account.refresh(force=True)
        return Response(MarketAccountSerializer(account, context={'request': request}).data)

    def create(self, request):
        serializer = NewAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not serializer.data or not isinstance(serializer.data, dict):
            return Response({'detail': 'No data provided.'}, status=400)
        if isinstance(serializer.validated_data, dict):
            account = serializer.validated_data['account']
        else:
            account = serializer.data.get('account')
        get_serializer = MarketAccountSerializer(instance=account, context=self.get_serializer_context())
        return Response(get_serializer.data, status=201)


class MarketSymbolViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MarketSymbol.objects.all()
    serializer_class = MarketSymbolSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = MarketSymbolFilter

    def get_queryset(self):
        return MarketSymbol.objects.select_related('market', 'symbol').all()

    @action(detail=False, methods=['get'], url_path='market/(?P<market>[^/.]+)', url_name='market')
    def market(self, request, market):
        """Return all symbols for a given market."""
        symbols = MarketSymbol.objects.filter(market__exchange_name=market.upper())
        serializer = MarketSymbolSerializer(symbols, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='(?P<market>[^/.]+)/(?P<symbol>[^/.]+)', url_name='symbol')
    def symbol(self, request, market, symbol):
        """Return a specific symbol for a given market."""
        symbol = MarketSymbol.objects.get(contract_type=MarketSymbol.ContractType.SPOT, market__exchange_name=market.upper(), name=symbol.upper())
        serializer = MarketSymbolSerializer(symbol, context={'request': request})
        return Response(serializer.data)


class GlobalSymbolViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = GlobalSymbol.objects.all()
    serializer_class = GlobalSymbolSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = GlobalSymbolFilter

    def get_queryset(self):
        return GlobalSymbol.objects.prefetch_related('tags', 'symbols').all()

    @action(detail=True, methods=['get', 'post'])
    def refresh(self, request, pk):
        symbol: GlobalSymbol = self.get_object()
        symbol.refresh()
        return Response(GlobalSymbolSerializer(symbol, context={'request': request}).data)


class StrategyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Strategy.objects.all()
    serializer_class = StrategySerializer


class SessionViewSet(viewsets.ModelViewSet):
    queryset = Session.objects.none()
    serializer_class = SessionSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = SessionFilter
    http_method_names = ['get', 'post', 'patch']

    def get_queryset(self):
        return Session.objects.select_related(
            'account', 
            'account__market', 
            'account__credentials', 
            'symbol', 
            'symbol__symbol', 
            'symbol__market', 
            'strategy', 
            'group',
        ).prefetch_related(
            Prefetch('account__market__symbols', queryset=MarketSymbol.objects.select_related('symbol', 'market')),
            'issues'
        ).exclude(group__isnull=False)

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return DraftSessionSerializer
        if self.request.method == 'PATCH':
            return SessionUpdateSerializer
        if self.request.method == 'GET':
            return SessionSerializer
        else:
            raise MethodNotAllowed(self.request.method)

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        get_serializer = SessionSerializer(instance=serializer.instance, context=self.get_serializer_context())
        headers = self.get_success_headers(get_serializer.data)
        return Response(get_serializer.data, status=201, headers=headers)

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, instance=self.get_object())
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        get_serializer = SessionSerializer(instance=serializer.instance, context=self.get_serializer_context())
        headers = self.get_success_headers(get_serializer.data)
        return Response(get_serializer.data, status=200, headers=headers)

    @action(detail=True, methods=['get'])
    def orders(self, request, pk):
        session = self.get_object()
        orders = session.orders.all()
        serializer = OrderSerializer(orders, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def signals(self, request, pk):
        session = self.get_object()
        signals = session.signals.all()
        serializer = SignalSerializer(signals, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def start(self, request, pk):
        session = self.get_object()
        validate_session_can_start(session)
        ll = LiveLoop.from_session(session)
        ll.run()
        session.status = Session.Status.ONGOING
        session.save()
        return Response({'detail': 'Session will start in a few seconds.'})

    @action(detail=True, methods=['post'])
    def pause(self, request, pk):
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
    def resume(self, request, pk):
        session = self.get_object()
        validate_session_can_start(session)
        ll = LiveLoop.from_session(session)
        ll.run()
        session.status = Session.Status.ONGOING
        session.save()
        return Response({'detail': 'Session will resume in a few seconds.'})

    @action(detail=True, methods=['post'])
    def terminate(self, request, pk):
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

    @action(detail=True, methods=['post'])
    def place(self, request, pk):
        session: Session = self.get_object()
        serializer = SessionOrderPlacementSerializer(data={**request.data, 'session': session.pk})
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        data = serializer.validated_data
        if not isinstance(data, dict) or not data:
            return Response({'detail': 'No data provided.'}, status=400)
        
        account: MarketAccount = session.account
        symbol: MarketSymbol = session.symbol
        side = data['side']
        funds = data.get('funds')
        deal_size = data.get('deal_size')
        oman = OrderManager(account.get_interface(), session)

        try:
            order = oman.place(symbol, side.lower(), deal_size, funds)
        except OrderPlacementError as e:
            return Response({'detail': f'Order placement error: {e!s}'}, status=400)
        return Response(OrderSerializer(order, context={'request': request}).data)


class SessionGroupViewSet(viewsets.ModelViewSet):
    queryset = SessionGroup.objects.all()
    serializer_class = SessionGroupSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = SessionGroupFilter

    def get_queryset(self):
        return SessionGroup.objects.select_related('symbol', 'interface').prefetch_related('sessions__orders', 'sessions__signals')

    @action(detail=True, methods=['get'])
    def sessions(self, request, pk=None):
        group = self.get_object()
        sessions = group.sessions.all()
        serializer = SessionSerializer(sessions, many=True, context={'request': request})
        return Response(serializer.data)


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    filter_backends = [DjangoFilterBackend]

    def get_queryset(self):
        return Order.objects.select_related('account', 'symbol', 'session').prefetch_related(
            'symbol__symbol',
            'symbol__market',
            'account__market',
            'account__credentials'
        )

    @action(detail=False, methods=['post'])
    def place(self, request):
        serializer = OrderPlacementSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        data = serializer.validated_data
        if not isinstance(data, dict) or not data:
            return Response({'detail': 'No data provided.'}, status=400)
        account: MarketAccount = data['account']
        symbol = data['symbol']
        side = data['side']
        funds = data.get('funds', 0)
        deal_size = data.get('deal_size', 0)
        oman = OrderManager(account.get_interface())
        try:
            order = oman.place(symbol, side.lower(), deal_size, funds)
        except OrderPlacementError as e:
            return Response({'detail': f'Order placement error: {e!s}'}, status=400)
        return Response(OrderSerializer(order, context={'request': request}).data)


class GroupOrderViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = GroupOrder.objects.all()
    serializer_class = GroupOrderSerializer
    filter_backends = [DjangoFilterBackend]


class SignalViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Signal.objects.all()
    serializer_class = SignalSerializer
    filter_backends = [DjangoFilterBackend]

    @action(detail=True, methods=['get'])
    def orders(self, request, pk):
        signal = self.get_object()
        orders = signal.orders.all()
        serializer = OrderSerializer(orders, many=True, context={'request': request})
        return Response(serializer.data)


class SubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer
    filter_backends = [DjangoFilterBackend]

class LiveLoopViewSet(viewsets.ViewSet):
    def list(self, request):
        return Response(LiveLoopSerializer(LIVELOOPS.values(), many=True).data)


class LoopGroupViewSet(viewsets.ViewSet):
    def list(self, request):
        return Response(LoopGroupSerializer(LOOPGROUPS.values(), many=True).data)


class HealthViewSet(viewsets.ViewSet):
    def list(self, request):
        sessions = Session.objects.filter(status=Session.Status.ONGOING, group__isnull=True)
        groups = SessionGroup.objects.filter(status=SessionGroup.Status.ONGOING)
        died_threads = []
        died_threads.extend([session.pk for session in sessions if not session.thread])
        died_threads.extend([group.pk for group in groups if not group.thread])
        return Response({
            'sessions': sessions.count(),
            'groups': groups.count(),
            'health': 'OK' if not died_threads else 'DEGRADED',
            'died_threads': died_threads
        })


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


class CandlesViewSet(viewsets.ViewSet):
    def list(self, request):
        return Response({'detail': 'Specify market, symbol and interval in the URI.'})

    def get(self, request, market, symbol, interval):
        market = Market.objects.get(exchange_name=market.upper())
        symbol = MarketSymbol.objects.get(contract_type=MarketSymbol.ContractType.SPOT, name=symbol.upper(), market=market)
        interface = symbol.market.get_interface()

        interval = interval.replace('min', ' min').replace('hour', ' hour').replace('day', ' day').replace('week', ' week').replace('month', ' month')

        candles = interface.get_last_klines(symbol, interval, limit=500)
        payload = [interface.format_candle(candle) for candle in candles]
        payload = sorted(payload, key=lambda x: x['time'])
        return Response({
            'market': market.exchange_name,
            'symbol': symbol.name,
            'interval': interval,
            'count': len(payload),
            'start': payload[0]['time'],
            'end': payload[-1]['time'],
            'candles': payload,
        })


class ContactFormViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ContactForm.objects.all()
    serializer_class = ContactFormSerializer
    http_method_names = ['post']


class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    pagination_class = None
