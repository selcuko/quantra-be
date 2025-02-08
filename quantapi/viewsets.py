from datetime import datetime, timedelta
import json

from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from django.core.management import call_command

import pytz
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from metrichub import  refresh_all_market_symbols, refresh_symbols_with_delta
from models import interval_to_minutes
from orderpulse.keeper import KeeperPool
from quantapi.filters import (GlobalSymbolFilter, MarketAccountFilter, MarketSymbolFilter, TagFilter)
from quantapi.models import (ContactForm, GlobalSymbol, Market,
                             MarketAccount, MarketSymbol, Tag)
from quantapi.serializers import (ContactFormSerializer, GlobalSymbolSerializer, MarketAccountSerializer,
                                  MarketSerializer, MarketSymbolSerializer, NewAccountSerializer, TagSerializer)


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
        iface = market.get_interface()
        iface.get_current_prices()
        market.refresh_from_db()
        return Response(MarketSerializer(market, context={'request': request}).data)


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
        return MarketSymbol.objects.select_related('market').prefetch_related(
            Prefetch('symbol', queryset=GlobalSymbol.objects.only('id', 'cid', 'coingecko_response', 'image')),
        )

    @action(detail=False, methods=['get'], url_path='market/(?P<market>[^/.]+)', url_name='market')
    def market(self, request, market):
        """Return all symbols for a given market."""
        symbols = MarketSymbol.objects.filter(market__exchange_name=market.upper())
        serializer = MarketSymbolSerializer(symbols, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='(?P<market>[^/.]+)/(?P<symbol>[^/.]+)', url_name='symbol')
    def symbol(self, request, market, symbol):
        """Return a specific symbol for a given market."""
        contract = request.query_params.get('contract', MarketSymbol.ContractType.SPOT)
        try:
            symbol = MarketSymbol.objects.get(contract_type=contract, market__exchange_name=market.upper(), name=symbol.upper())
        except MarketSymbol.DoesNotExist:
            return Response({'detail': 'Symbol not found.'}, status=404)
        serializer = MarketSymbolSerializer(symbol, context={'request': request})
        return Response(serializer.data)


class GlobalSymbolViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = GlobalSymbol.objects.all()
    serializer_class = GlobalSymbolSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = GlobalSymbolFilter
    lookup_field = 'cid'
    lookup_url_kwarg = 'pk'

    def get_queryset(self):
        return GlobalSymbol.objects.all().prefetch_related(
            Prefetch('symbols', queryset=MarketSymbol.objects.only('market', 'contract_type', 'symbol', 'base', 'quote', 'name').select_related('market')),
            Prefetch('tags', queryset=Tag.objects.all()),
        )

    @action(detail=False, methods=['get'], url_path='cid/(?P<pk>[^/.]+)', url_name='cid')
    def cid(self, request, pk):
        try:
            symbol = GlobalSymbol.objects.get(cid=pk)
            return Response(self.serializer_class(instance=symbol, context={'request': request}).data)
        except GlobalSymbol.DoesNotExist:
            return Response({'detail': 'Symbol not found.'}, status=404)

    @action(detail=True, methods=['get', 'post'])
    def refresh(self, request, pk):
        symbol: GlobalSymbol = self.get_object()
        if not (datetime.now(tz=pytz.UTC) - symbol.data_updated) < timedelta(minutes=15):
            symbol.refresh()
            symbol.refresh_from_db()
        return Response(GlobalSymbolSerializer(symbol, context={'request': request}).data)

    @action(detail=False, methods=['get', 'post'], url_path='refresh', url_name='refresh-all')
    def refresh_all(self, request):
        refresh_symbols_with_delta()
        refresh_all_market_symbols()
        call_command('match_symbols')
        call_command('reload_cg_tags')
        call_command('match_tags')
        return Response()


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
        results = Tag.objects.prefetch_related(
            Prefetch('symbols', queryset=GlobalSymbol.objects.order_by('-volume')[:3].only('id', 'cid', 'display', 'base', 'image', 'markets'), to_attr='top_symbols'),
        )
        return results

    def list(self, request):
        return super().list(request)


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
                'started': keeper.started,
                'connections': connections,
                'buckets': MiniOrderbookConsumer.dispatcher.channels.get(keeper, []),
                'state': keeper.state(),
                'terminate': str(MiniOrderbookConsumer.dispatcher.shutdown_schedules.get(keeper, None)),
            }
            payloads.append(payload)
        return Response(payloads)


class ReverseProxyView(viewsets.ViewSet):
    def get(self, request, url):
        from django.http import HttpResponse
        import requests
        query_params = request.query_params
        response = requests.get(url + '?' + '&'.join([f'{k}={v}' for k, v in query_params.items()]))
        return HttpResponse(response.content, content_type=response.headers['content-type'])
    
    def post(self, request, url):
        from django.http import HttpResponse
        import requests
        query_params = request.query_params
        response = requests.post(url + '?' + '&'.join([f'{k}={v}' for k, v in query_params.items()]), data=request.data)
        return HttpResponse(response.content, content_type=response.headers['content-type'])
