from datetime import datetime, timedelta
import json

from django.db.models import Prefetch, Count, Q
from django_filters.rest_framework import DjangoFilterBackend
import pytz
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.response import Response

from cache import LIVELOOPS
from loops import LiveLoop
from markets.errors import OrderPlacementError
from models import interval_to_minutes
from order import OrderManager
from orderpulse.keeper import KeeperPool
from quantapi.filters import (GlobalSymbolFilter, MarketAccountFilter, MarketSymbolFilter,
                              SessionFilter, SessionGroupFilter, TagFilter)
from quantapi.models import (ContactForm, GlobalSymbol, GroupOrder, Market,
                             MarketAccount, MarketSymbol, Order,
                             Session, SessionGroup, Signal, Strategy,
                             Subscription, Tag)
from quantapi.serializers import (ContactFormSerializer, DraftSessionSerializer,
                                  GlobalSymbolSerializer, GroupOrderSerializer,
                                  
                                  MarketAccountSerializer,
                                  MarketSerializer, MarketSymbolSerializer, NewAccountSerializer,
                                  OrderPlacementSerializer, OrderSerializer,
                                  SessionGroupSerializer,
                                  SessionOrderPlacementSerializer,
                                  SessionSerializer, SessionUpdateSerializer,
                                  SignalSerializer, StrategySerializer,
                                  SubscriptionSerializer, TagSerializer)
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

    @action(detail=True, methods=['get'])
    def refresh(self, request, pk):
        market: Market = self.get_object()
        market.get_interface()
        market.refresh_from_db()
        return Response(MarketSerializer(market, context={'request': request}).data)

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
        return MarketSymbol.objects.select_related('market', 'symbol')

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
    ordering = ['metrics__market_cap']

    def get_queryset(self):
        return GlobalSymbol.objects.prefetch_related(
            Prefetch('symbols', queryset=MarketSymbol.objects.select_related('market')),
            Prefetch('tags', queryset=Tag.objects.select_related('metrics')),
        ).select_related('metrics')

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


class CandlesViewSet(viewsets.ViewSet):
    def list(self, request):
        return Response({'detail': 'Specify market, symbol and interval in the URI.'})

    def get(self, request, market, symbol, interval):
        start = request.query_params.get('start')
        end = request.query_params.get('end')
        contract_type = request.query_params.get('contract_type', 'spot')
        limit = int(request.query_params.get('limit', 500))
        interval = interval.replace('min', ' min').replace('hour', ' hour').replace('day', ' day').replace('week', ' week').replace('month', ' month')

        if end:
            end_date = datetime.fromisoformat(end)
        else:
            end_date = datetime.now(tz=pytz.UTC)
        if start:
            start_date = datetime.fromisoformat(start)
        else:
            start_date = end_date - timedelta(minutes=interval_to_minutes(interval) * limit)

        if start_date >= end_date:
            return Response({'detail': 'Start date must be before end date.'}, status=400)
        elif (end_date - start_date) > timedelta(minutes=interval_to_minutes(interval) * limit):
            start_date = end_date - timedelta(minutes=interval_to_minutes(interval) * limit)
        if start_date < datetime(2017, 1, 1, tzinfo=pytz.UTC):
            start_date = datetime(2017, 1, 1, tzinfo=pytz.UTC)
        if end_date < datetime(2017, 1, 1, tzinfo=pytz.UTC):
            end_date = datetime(2017, 1, 1, tzinfo=pytz.UTC)

        market = Market.objects.get(exchange_name=market.upper())
        symbol = MarketSymbol.objects.get(contract_type=contract_type.upper(), name=symbol.upper(), market=market)

        interface = symbol.market.get_interface()

        if not start and not end:
            candles = interface.get_last_klines(symbol, interval, limit=limit)
        else:
            candles = interface.get_klines(symbol, interval, start_date, end_date)

        payload = [interface.format_candle(candle) for candle in candles]
        payload = sorted(payload, key=lambda x: x['time'])
        return Response({
            'market': market.exchange_name,
            'symbol': symbol.name,
            'interval': interval,
            'count': len(payload),
            'start': payload[0]['time'] if payload else None,
            'end': payload[-1]['time'] if payload else None,
            'candles': payload,
        })


class ContactFormViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ContactForm.objects.all()
    serializer_class = ContactFormSerializer
    http_method_names = ['post']


class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = TagFilter
    lookup_field = 'name'

    def get_queryset(self):
        return Tag.objects.select_related('metrics').prefetch_related(
            Prefetch('symbols', queryset=GlobalSymbol.objects.select_related('metrics')),
        )


class KeeperView(viewsets.ViewSet):
    def list(self, request):
        from orderpulse.consumers.miniorderbook import MiniOrderbookConsumer
        keepers = KeeperPool.pool.values()
        payloads = []
        for keeper in keepers:
            connections = MiniOrderbookConsumer.dispatcher.connections.get(keeper, [])
            payload = {
                'symbol': str(keeper.symbol),
                'market': keeper.market,
                'status': 'running' if keeper.started else 'stopped',
                'connections': connections,
                'buckets': MiniOrderbookConsumer.dispatcher.channels.get(keeper, []),
            }
            payloads.append(payload)
        return Response(payloads)


class CategoryViewSet(viewsets.ModelViewSet):
    class Meta:
        model = Tag
        fields = ['name']
