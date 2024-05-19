import json
import threading
from datetime import datetime, timedelta
import traceback

import pytz
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views import View
from django.core.cache import cache


from backtest import async_analyze
from liveloop import LiveLoop
from logger import logger
from markets.errors import (InsufficientBalance, MarketDisabledTrading,
                            SymbolNotInMarket)
from order import OrderManager
from quantapi.analytics import MarketAnalytics, TotalSessionAnalytics
from quantapi.models import (Backtest, GlobalSymbol, Market, MarketSymbol,
                             Order, Session, Strategy)
from strategy import get_strategy
from django.contrib import messages



class HomeView(View):
    def get(self, request):
        sessions = Session.objects.filter(status=Session.Status.ONGOING, symbol__market__mainnet_enabled=True).order_by('-started').prefetch_related('symbol', 'symbol__market')
        recent_orders = Order.objects.filter(signal__session__in=sessions, status=Order.Status.FILLED).order_by('-created_at').prefetch_related('session', 'session__symbol')[:8]

        ma = MarketAnalytics()
        sa = TotalSessionAnalytics(sessions)

        return render(request, 'index.html', {
            'sessions': sessions, 
            'orders': recent_orders,
            'analytics': { 'market': ma , 'session': sa },
        })


class SessionDetailView(View):
    def get(self, request, pk):
        session = Session.objects.prefetch_related('orders', 'signals').get(pk=pk)
        signals = session.signals
        orders = session.orders
        market = session.symbol.market
        symbol = session.symbol
        orders = orders.order_by('-created_at')
        signals = signals.order_by('-timestamp')
        market_assets = json.loads(market.assets or '{}').get(symbol.base, 0)
        return render(request, 'session-detail.html', {
            'session': session, 
            'orders': orders, 
            'signals': signals, 
            'market': market, 
            'symbol': symbol,
            'buy_enabled': session.capital >= 5,
            'sell_enabled': session.assets > 0,
            'market_assets': market_assets,
        })


class SessionListView(View):
    def get(self, request, query=None):
        if query is None:
            query = Session.objects.all().prefetch_related('symbol', 'symbol__market')
        query = query.order_by('-started')
        paginator = Paginator(query, 20)
        page_number = request.GET.get('page')
        page = paginator.get_page(page_number)
        markets = Market.objects.filter(trading_enabled=True).order_by('exchange_name')
        return render(request, 'session-list.html', {
            'sessions': page, 
            'markets': markets,
            'selected_market': request.session.get('session-list-market', 'all'),
            'selected_status': request.session.get('session-list-status', 'all'),
            'selected_time': request.session.get('session-list-time', 'all'),
        })
    
    def post(self, request):
        request.session.pop('message', None)
        time_map = {
            '7d': timedelta(days=7),
            '30d': timedelta(days=30),
            '1y': timedelta(days=365),
            'all': timedelta(days=365*100),
        }
        request.session['session-list-status'] = request.POST.get('status', request.session.get('session-list-status', 'all'))
        request.session['session-list-market'] = request.POST.get('market', request.session.get('session-list-market', 'all'))
        request.session['session-list-time'] = request.POST.get('time', request.session.get('session-list-time', 'all'))
        query = Session.objects.all()
        if request.session['session-list-status'] != 'all':
            query = query.filter(status=request.session['session-list-status'])
        if request.session['session-list-market'] != 'all':
            query = query.filter(symbol__market__id=request.session['session-list-market'])
        if end_at := time_map.get(request.session['session-list-time']) :
            query = query.filter(started__gte=datetime.now(pytz.UTC) - end_at)
        else:
            request.session['message'] = {
                'type': 'error',
                'text': f'Invalid time range: {request.session["session-list-time"]}'
            }
        return self.get(request, query=query)



class SessionInitView(View):
    def get(self, request):
        markets = Market.objects.filter(trading_enabled=True).order_by('exchange_name')
        strategies = Strategy.objects.all().order_by('-version')
        return render(request, 'session-init.html', {'markets': markets, 'strategies': strategies})

    def post(self, request, *args, **kwargs):
        form_data = request.POST
        try:
            market = Market.objects.get(pk=form_data['market'])
            imarket = market.get_interface()
            symbol_name = form_data['symbol'].upper().replace('-', '').replace('/', '').replace('USDT', '') + '-USDT'
            if not imarket.has_symbol(symbol_name):
                raise SymbolNotInMarket(f'Symbol {symbol_name} not found in market {market.exchange_name}')
            symbol = MarketSymbol.objects.get(name=symbol_name, market=market)
            if not symbol.spot_trading_enabled:
                raise MarketDisabledTrading(f'{market.exchange_name} does not allow {symbol.name} in SPOT trading')
            if not market.is_valid_session_type((session_type := form_data['type'])):
                raise MarketDisabledTrading(f'Market {market.exchange_name} does not support session type {session_type}')
            if (capital_limit := float(form_data['capital'])) > imarket.capital and session_type in [Session.Type.LIVE_SANDBOX, Session.Type.LIVE_MAINNET]:
                raise InsufficientBalance(f'Capital limit {capital_limit} is more than market capital {imarket.capital}')
            if (asset_limit := float(form_data['assets'])) > imarket.assets.get(symbol.base, 0) and session_type in [Session.Type.LIVE_SANDBOX, Session.Type.LIVE_MAINNET]:
                raise InsufficientBalance(f'Asset limit {asset_limit} is more than market assets {imarket.assets}')
            candle_source = form_data.get('candle_source', 'trade')
            strategy_name = form_data.get('strategy', 'v1')
        except Exception as e:
            return render(request, 'session-init.html', {'markets': Market.objects.filter(trading_enabled=True).order_by('exchange_name'), 'form_error': traceback.format_exc()})
        try:
            ll = LiveLoop(
                symbol=symbol.name,
                market=market,
                strategy=get_strategy(strategy_name)({
                    'source': form_data.get('source', 'close'),
                }),
                capital_limit=capital_limit,
                asset_limit=asset_limit,
                freq=form_data['freq'],
                session_type=session_type,
                use_heikin_ashi=form_data.get('candle_type', 'standard') == 'heikin_ashi',
            )
            if candle_source == 'trade':
                ll.run(match_engine=True)
            elif candle_source == 'websocket':
                ll.run(websocket=True)
            else:
                ll.run(polling=True)
        except Exception as e:
            raise e
        return redirect('session-detail', pk=ll.session.pk)


class SessionUpdateView(View):
    def post(self, request, pk):
        session = Session.objects.get(pk=pk)

        if 'session_buy_enabled' in request.POST:
            session.buy_enabled = bool(int(request.POST.get('session_buy_enabled', 0)))
        if 'session_sell_enabled' in request.POST:
            session.sell_enabled = bool(int(request.POST.get('session_sell_enabled', 0)))

        if 'session_buy' in request.POST and float(request.POST.get('session_buy', 0)) > 0:
            iface = session.symbol.market.get_interface()
            session.update(iface)
            amt = float(request.POST.get('session_buy'))
            corrected_amt = min(amt, session.capital)
            msg = None
            if amt != corrected_amt:
                msg = f'Manual buy amount {amt} exceeds available capital {session.capital} USDT. Corrected to {corrected_amt} USDT.'
                logger.warning(msg, extra={'prefix': repr(session), 'type': 'ORDER'})
            order_manager = OrderManager(iface, session)
            try:
                order = order_manager.place(session.symbol, 'buy', deal_funds=corrected_amt)
            except Exception as e:
                msg = f'Failed to place buy order: {e!r}'
                logger.error(msg, extra={'prefix': repr(session), 'type': 'ORDER'})
                messages.add_message(request, messages.ERROR, msg)
                return redirect('session-detail', pk=session.pk)
            order.force = True
            if msg:
                order.add_message(msg)
            order.save()
            if order.status == Order.Status.FILLED and order.deal_size and order.deal_funds:
                session.capital -= order.deal_funds
                session.assets += order.deal_size
                iface.cache_to_db(force=True)
                messages.add_message(request, messages.SUCCESS, f'Bought {order.deal_size} {session.symbol.base} for {order.deal_funds} USDT')
            else:
                msg = f'Order failed to fill: {order.details}'
                logger.error(msg, extra={'prefix': repr(session), 'type': 'ORDER'})
                messages.add_message(request, messages.ERROR, msg)

        if 'session_sell' in request.POST and float(request.POST.get('session_sell', 0)) > 0:
            iface = session.symbol.market.get_interface()
            session.update(iface)
            amt = float(request.POST.get('session_sell'))
            corrected_amt = min(amt, session.assets)
            msg = None
            if amt != corrected_amt:
                msg = f'Manual sell amount {amt} exceeds available assets {session.assets} {session.symbol.base}. Corrected to {corrected_amt} {session.symbol.base}.'
                logger.warning(msg, extra={'prefix': repr(session), 'type': 'ORDER'})
            order_manager = OrderManager(iface, session)
            try:
                order = order_manager.place(session.symbol, 'sell', deal_size=corrected_amt)
            except Exception as e:
                msg = f'Failed to place sell order: {e!r}'
                logger.error(msg, extra={'prefix': repr(session), 'type': 'ORDER'})
                messages.add_message(request, messages.ERROR, msg)
                return redirect('session-detail', pk=session.pk)
            order.force = True
            if msg:
                order.add_message(msg)
            order.save()
            if order.status == Order.Status.FILLED and order.deal_size and order.deal_funds:
                session.capital += order.deal_funds
                session.assets -= order.deal_size
                iface.cache_to_db(force=True)
                messages.add_message(request, messages.SUCCESS, f'Sold {order.deal_size} {session.symbol.base} for {order.deal_funds} USDT')
            else:
                msg = f'Order failed to fill: {order.messages_raw}'
                logger.error(msg, extra={'prefix': repr(session), 'type': 'ORDER'})
                messages.add_message(request, messages.ERROR, msg)

        if 'capital_update' in request.POST:
            session.capital = float(request.POST.get('capital_update', 0))
        if 'asset_update' in request.POST:
            session.assets = float(request.POST.get('asset_update', 0))


        session.save()
        return redirect('session-detail', pk=session.pk)

    @staticmethod
    def resume(request, pk):
        session = Session.objects.get(pk=pk)
        if not session.status == Session.Status.PAUSED:
            return render(request, 'session-detail.html', {'session': session, 'error': {
                'type': 'error',
                'text': 'Session is not paused.'
            }})
        session.status = Session.Status.ONGOING
        session.save()
        session.resume()
        return redirect('session-detail', pk=session.pk)

    @staticmethod
    def pause(request, pk):
        session = Session.objects.get(pk=pk)
        if not session.status == Session.Status.ONGOING:
            return render(request, 'session-detail.html', {'session': session, 'error': {
                'type': 'error',
                'text': 'Session is not ongoing.'
            }})
        session.status = Session.Status.PAUSED
        session.ended = datetime.now(pytz.UTC)
        session.save()
        liveloop:LiveLoop = cache.get(f'session_{session.pk}')
        if liveloop:
            liveloop.stop()
        return redirect('session-detail', pk=session.pk)

    @staticmethod
    def terminate(request, pk):
        session = Session.objects.get(pk=pk)
        if session.status not in [Session.Status.ONGOING, Session.Status.PAUSED]:
            return render(request, 'session-detail.html', {'session': session, 'error': {
                'type': 'error',
                'text': 'Session is not ongoing.'
            }})
        session.status = Session.Status.COMPLETED
        session.ended = datetime.now(pytz.UTC)
        session.planned_shutdown = datetime.now(pytz.UTC)
        session.save()
        liveloop:LiveLoop = cache.get(f'session_{session.pk}')
        if liveloop:
            liveloop.stop()
        return redirect('session-detail', pk=session.pk)


class MarketListView(View):
    def get(self, request):
        markets = Market.objects.filter(trading_enabled=True).order_by('exchange_name')
        return render(request, 'market-list.html', { 'markets': markets })


class MarketDetailView(View):
    def get(self, request, pk):
        market = Market.objects.get(pk=pk)
        interface = market.get_interface()
        interface.cache_to_db(force=True)
        symbols = MarketSymbol.objects.filter(market=market)
        assets = json.loads(market.assets or '{}')
        available_assets = {symbol: assets[symbol] for symbol in assets if assets[symbol] > 0}
        return render(request, 'market-detail.html', {'market': market, 'symbols': symbols, 'interface': interface, 'available_assets': available_assets})

    @staticmethod
    def raw(request, pk):
        market = Market.objects.get(pk=pk)
        return JsonResponse({
            'assets': json.loads(market.assets) if market.assets else {},
            'prices': json.loads(market.prices) if market.prices else {},
            'capital': market.usdt,
            'equity': market.equity,
            'updated': market.assets_updated_at,
            'available_capital': market.available_capital,
        })


class RunningThreadsView(View):
    def get(self, request):
        threads = threading.enumerate()
        return render(request, 'threads.html', {'threads': threads})


class BacktestInitView(View):
    def get(self, request):
        markets = set(Market.objects.filter(trading_enabled=True).order_by('exchange_name').values_list('exchange_name', flat=True))
        return render(request, 'backtest-init.html', {'markets': markets})

    def post(self, request):
        form_data = request.POST
        exchange = form_data['market']
        symbol = form_data['symbol']
        symbol = symbol.upper().replace('-', '').replace('/', '').replace('USDT', '') + '-USDT'
        freq = form_data['freq']
        start = form_data['start']
        end = form_data.get('end', None)
        stoch_length = int(form_data.get('stoch_length', 3))
        volume_ma = int(form_data.get('volume_ma', 20))
        source = form_data.get('source', 'close')
        candle_type = form_data.get('candle_type', 'standard')
        if end:
            end = datetime.strptime(end, '%Y-%m-%d').replace(tzinfo=pytz.UTC)
        else:
            end = None
        start = datetime.strptime(start, '%Y-%m-%d').replace(tzinfo=pytz.UTC)

        backtest = async_analyze(
            market=exchange, 
            symbol=symbol, 
            freq=freq, 
            start=start, 
            end=end, 
            candle_type=candle_type,
            stoch_length=stoch_length,
            volume_ma=volume_ma,
            source=source,
        )
        return redirect('backtest-result', pk=backtest.pk)


class BacktestResultView(View):
    def get(self, request, pk):
        backtest = Backtest.objects.get(id=pk)
        report = backtest.report
        if backtest.report and backtest.status == Backtest.Status.COMPLETED:
            report = open(f'{backtest.report}').read()
            report = json.loads(report)
        return render(request, 'backtest-result.html', {'backtest': backtest, 'report': report})


class WatchdogView(View):
    def get(self, request):
        from watchdog import watchdog
        return render(request, 'watchdog.html', context={ 'watchdog': watchdog() })


class OrderManagementView(View):
    def get(self, request):
        markets = Market.objects.filter(trading_enabled=True).order_by('exchange_name').order_by('exchange_name')
        return render(request, 'order-management.html', context={ 'markets': markets })
    
    def post(self, request):
        payload = request.POST
        if not all((
            payload.get('market'),
            payload.get('symbol'),
            payload.get('side') in ['BUY', 'SELL'],
            payload.get('amount'),
        )):
            messages.error(request, f'Invalid order parameters: {payload}')
            return redirect('order-management')
        market = Market.objects.get(pk=payload['market'])
        symbol_name = payload['symbol']
        symbol_name = symbol_name.upper().replace('-', '').replace('/', '').replace('USDT', '') + '-USDT'
        symbol = MarketSymbol.objects.get(name=symbol_name, market=market)
        interface = market.get_interface()
        amount = float(payload['amount'])
        order_manager = OrderManager(interface)
        try:
            order = None
            if payload['side'] == 'BUY':
                order = order_manager.place(symbol, 'buy', deal_funds=amount, silent=False)
            elif payload['side'] == 'SELL':
                order = order_manager.place(symbol, 'sell', deal_size=amount, silent=False)
            interface.cache_to_db(force=True)
            messages.success(request, f'Order placed: {order!s}')
        except Exception as e:
            messages.error(request, f'Failed to place order: {e!r}')
        return redirect('order-management')

class PriceView(View):
    def get(self, request):
        response = {
            'message': 'OK',
            'price': None,
            'updated': None,
        }
        params = request.GET
        symbol = params.get('symbol', '').upper()
        market_id = params.get('market')
        if not (symbol and market_id):
            response['message'] = 'Invalid symbol or market'
            return JsonResponse(response)
        if not '-' in symbol:
            symbol += '-USDT'

        market = Market.objects.get(pk=market_id)
        prices = json.loads(market.prices or '{}')
        if not symbol in prices:
            response['message'] = f'No price found for {symbol}'
            return JsonResponse(response)
        response['price'] = prices[symbol]
        response['updated'] = market.assets_updated_at
        return JsonResponse(response)



class CoinScanView(View):
    def get(self, request):
        return render(request, 'symbol-scan.html')

    def post(self, request):
        payload = json.loads(request.body.decode('utf-8'))
        query = {}
        if payload.get('volumeMin'):
            query['volume__gte'] = int(payload['volumeMin'])
        if payload.get('volumeMax'):
            query['volume__lte'] = int(payload['volumeMax'])
        if payload.get('atlProxMax'):
            query['atl_prox__lte'] = float(payload['atlProxMax'])
        if payload.get('atlProxMin'):
            query['atl_prox__gte'] = float(payload['atlProxMin'])
        if payload.get('athProxMax'):
            query['ath_prox__lte'] = float(payload['athProxMax'])
        if payload.get('athProxMin'):
            query['ath_prox__gte'] = float(payload['athProxMin'])
        if payload.get('supplyMax'):
            query['supply_ratio__lte'] = float(payload['supplyMax'])
        if payload.get('supplyMin'):
            query['supply_ratio__gte'] = float(payload['supplyMin'])
        if payload.get('marketcapMin'):
            query['market_cap__gte'] = int(payload['marketcapMin'])
        if payload.get('marketcapMax'):
            query['market_cap__lte'] = int(payload['marketcapMax'])
        if payload.get('volToMcapMin'):
            query['volume24h_to_mcap__gte'] = float(payload['volToMcapMin'])
        if payload.get('volToMcapMax'):
            query['volume24h_to_mcap__lte'] = float(payload['volToMcapMax'])
        if payload.get('sortBy'):
            sort = payload['sortBy']
            if sort == 'symbol':
                sort = '-volume'
        else:
            sort = '-volume'
        if payload.get('search'):
            query['base__icontains'] = payload['search'].replace(' ', '')
        market_query = Q()
        if payload.get('markets'):
            markets = payload['markets']
            for market in markets:
                if market == 'NOTNULL':
                    market_query &= Q(available_markets__isnull=False) & ~Q(available_markets='') & ~Q(available_markets='[]')
                else:
                    market_query &= Q(available_markets__icontains=market)
        start = 0
        end = 50
        if payload.get('start'):
            start = int(payload['start'])
        if payload.get('end'):
            end = int(payload['end'])
        sort_col = sort.replace('-', '')
        globals = GlobalSymbol.objects.filter(volume__gte=100)
        globals = globals.exclude(**{f'{sort_col}__isnull': True}).exclude(is_stablecoin=True)
        symbols = globals.filter(**query).filter(market_query).order_by(sort)
        count = symbols.count()
        symbols = symbols[start:end]
        response = {'symbols': GlobalSymbol.batch_to_json(symbols), 'count': count}
        return JsonResponse(response, safe=False)


class SymbolView(View):
    def get(self, request, cid):
        try:
            symbol = GlobalSymbol.objects.get(cid=cid)
        except GlobalSymbol.DoesNotExist:
            return render(request, 'symbol-detail.html', {'error': f'Symbol CID={cid} not found.'})
        return render(request, 'symbol-detail.html', {'symbol': symbol})


class FavoritesView(View):
    def get(self, request):
        favorites = GlobalSymbol.objects.filter(is_favorite=True)
        return render(request, 'symbol-favorites.html', {'symbols': favorites})


    def post(self, request):
        payload = json.loads(request.body.decode('utf-8'))
        query = {}
        if payload.get('volumeMin'):
            query['volume__gte'] = int(payload['volumeMin'])
        if payload.get('volumeMax'):
            query['volume__lte'] = int(payload['volumeMax'])
        if payload.get('atlProxMax'):
            query['atl_prox__lte'] = float(payload['atlProxMax'])
        if payload.get('atlProxMin'):
            query['atl_prox__gte'] = float(payload['atlProxMin'])
        if payload.get('athProxMax'):
            query['ath_prox__lte'] = float(payload['athProxMax'])
        if payload.get('athProxMin'):
            query['ath_prox__gte'] = float(payload['athProxMin'])
        if payload.get('supplyMax'):
            query['supply_ratio__lte'] = float(payload['supplyMax'])
        if payload.get('supplyMin'):
            query['supply_ratio__gte'] = float(payload['supplyMin'])
        if payload.get('marketcapMin'):
            query['market_cap__gte'] = int(payload['marketcapMin'])
        if payload.get('marketcapMax'):
            query['market_cap__lte'] = int(payload['marketcapMax'])
        if payload.get('volToMcapMin'):
            query['volume24h_to_mcap__gte'] = float(payload['volToMcapMin'])
        if payload.get('volToMcapMax'):
            query['volume24h_to_mcap__lte'] = float(payload['volToMcapMax'])
        if payload.get('sortBy'):
            sort = payload['sortBy']
            if sort == 'symbol':
                sort = '-volume'
        else:
            sort = '-volume'
        if payload.get('search'):
            query['base__icontains'] = payload['search'].replace(' ', '')
        market_query = Q()
        if payload.get('markets'):
            markets = payload['markets']
            for market in markets:
                if market == 'NOTNULL':
                    market_query &= Q(available_markets__isnull=False) & ~Q(available_markets='') & ~Q(available_markets='[]')
                else:
                    market_query &= Q(available_markets__icontains=market)
        start = 0
        end = 50
        if payload.get('start'):
            start = int(payload['start'])
        if payload.get('end'):
            end = int(payload['end'])
        sort_col = sort.replace('-', '')
        globals = GlobalSymbol.objects.filter(volume__gte=100)
        globals = globals.exclude(**{f'{sort_col}__isnull': True}).exclude(tags__contains='stablecoin').exclude(is_favorite=False)
        symbols = globals.filter(**query).filter(market_query).order_by(sort)
        count = symbols.count()
        symbols = symbols[start:end]
        response = {'symbols': GlobalSymbol.batch_to_json(symbols), 'count': count}
        return JsonResponse(response, safe=False)

    @staticmethod
    def favorite(request):
        payload = json.loads(request.body.decode('utf-8'))
        symbol_cid = payload.get('cid')
        if not symbol_cid:
            return JsonResponse({'error': 'Symbol CID is required.'})
        is_favorite = payload.get('isFavorite')
        try:
            symbol = GlobalSymbol.objects.get(cid=symbol_cid)
        except GlobalSymbol.DoesNotExist:
            return JsonResponse({'error': f'Symbol CID={symbol_cid} not found.'})
        if symbol.is_favorite != is_favorite:
            symbol.is_favorite = is_favorite
            symbol.save()
        return JsonResponse({'success': f'Symbol {symbol_cid} is now {"added to" if is_favorite else "removed from"} favorites.'})


class OrderBookInitView(View):
    def get(self, request):
        return render(request, 'orderbook.html')


class OrderBookView(View):
    @staticmethod
    def search(request):
        query = request.GET.get('q')
        symbols = MarketSymbol.objects.filter(name__contains=query)
        symbol_names = symbols.values_list('name', flat=True)
        return JsonResponse({'symbols': list(set(symbol_names))})

    def get(self, request):
        if not request.GET.get('symbol'):
            return render(request, 'orderbook.html')
        orderbook = {
            "asks": [{ 'price': x*2, 'amount': x} for x in range(100, 200) ],
            "bids": [{ 'price': x*2, 'amount': x} for x in range(1, 100) ],
        }
        asks = [ x for x in sorted(orderbook['asks'], key=lambda x: x['price'], reverse=True) if x['amount'] > 0]
        bids = [ x for x in sorted(orderbook['bids'], key=lambda x: x['price'], reverse=True) if x['amount'] > 0]
        return render(request, 'orderbook-detail.html', {"orderbook_name": "OBNAME", "asks": asks, "bids": bids})


