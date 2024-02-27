import json
import re
import threading
from datetime import datetime, timedelta

import pytz
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.views import View
from regex import F
from backtest import async_analyze
from django.http import HttpResponse, JsonResponse, response
from livetest import LiveLoop
from markets.errors import InsufficientBalance, MarketDisabledTrading, SymbolNotInMarket
from quantapi.analytics import MarketAnalytics, TotalSessionAnalytics
from quantapi.models import (Backtest, Market, Order, Session, Signal,
                             Symbol, Strategy as StrategyModel)
from strategy import get_strategy


def get_open_position(session):
    # get last filled order
    orders = Order.objects.filter(signal__session=session, status=Order.Status.FILLED)
    if not orders:
        return None
    last_order = orders.order_by('-timestamp')[0]
    if last_order.signal.side == 'BUY':
        return last_order
    else:
        return None


class HomeView(View):
    def get(self, request):
        sessions = Session.objects.filter(status=Session.Status.ONGOING, symbol__market__mainnet_enabled=True).order_by('-started')
        session_ctx = []
        total_open_positions = []
        for session in sessions:
            recent_orders = Order.objects.filter(signal__session=session)
            open_position = get_open_position(session)
            current_price = session.last_price or 0
            if open_position:
                capital_delta = (session.assets * current_price - session.initial_capital) / session.initial_capital * 100 if session.initial_capital else 0
                capital_delta_pct = capital_delta / session.initial_capital * 100 if session.initial_capital else 0
                open_position_delta = (current_price - open_position.price)
                open_position_delta_pct = open_position_delta / open_position.price * 100 if open_position.price else 0
                total_open_positions.append(open_position_delta_pct)
            else:
                capital_delta = (session.capital - session.initial_capital) if session.initial_capital else 0
                capital_delta_pct = capital_delta / session.initial_capital * 100 if session.initial_capital else 0
                open_position_delta = None
                open_position_delta_pct = None
            session_ctx.append({
                'session': session,
                'total_orders': recent_orders.count(),
                'total_signals': Signal.objects.filter(session=session).count(),
                'open_position': open_position,
                'current_price': current_price,
                'capital_delta': capital_delta,
                'capital_delta_pct': capital_delta_pct,
                'open_position_delta': open_position_delta,
                'open_position_delta_pct': open_position_delta_pct,
            })

        recent_orders = Order.objects.filter(signal__session__in=sessions, status=Order.Status.FILLED).order_by('-timestamp')[:8]

        ma = MarketAnalytics()
        sa = TotalSessionAnalytics(sessions)

        return render(request, 'index.html', {
            'sessions': sessions, 
            'orders': recent_orders,
            'open_positions': total_open_positions,
            'analytics': { 'market': ma , 'session': sa },
            'total_open_positions': total_open_positions,
            'total_capital': sum([session.capital for session in sessions]),
        })


class SessionDetailView(View):
    def get_open_position(self, session):
        # get last filled order
        orders = Order.objects.filter(signal__session=session, status=Order.Status.FILLED)
        if not orders:
            return None
        last_order = orders.order_by('-timestamp')[0]
        if last_order.signal.side == 'BUY':
            return last_order
        else:
            return None

    def get(self, request, pk):
        session = Session.objects.get(pk=pk)
        signals = Signal.objects.filter(session=session)
        orders = Order.objects.filter(signal__in=signals)
        error = request.session.pop('error', None)
        market = session.symbol.market
        message = request.session.pop('message', None)
        open_position = self.get_open_position(session)
        return render(request, 'session-detail.html', {
            'session': session, 
            'error': error, 
            'orders': orders, 
            'signals': signals, 
            'market': market, 
            'message': message, 
            'open_position': open_position, 
            'buy_enabled': session.capital > 5,
            'sell_enabled': session.assets > 0,
            })


class SessionListView(View):
    def get(self, request, query=None):
        if query is None:
            query = Session.objects.all()
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
        return render(request, 'session-init.html', {'markets': markets})

    def post(self, request, *args, **kwargs):
        form_data = request.POST
        print(form_data)
        markets = Market.objects.filter(trading_enabled=True).order_by('exchange_name')
        try:
            market = Market.objects.get(pk=form_data['market'])
            imarket = market.get_interface()
            symbol_name = form_data['symbol'].upper().replace('-', '').replace('/', '').replace('USDT', '') + '-USDT'
            if not imarket.has_symbol(symbol_name):
                raise SymbolNotInMarket(f'Symbol {symbol_name} not found in market {market.exchange_name}')
            symbol = Symbol.objects.get(name=symbol_name, market=market)
            if not symbol.spot_trading_enabled:
                raise MarketDisabledTrading(f'{market.exchange_name} does not allow {symbol.name} in SPOT trading')
            if not market.is_valid_session_type((session_type := form_data['type'])):
                raise MarketDisabledTrading(f'Market {market.exchange_name} does not support session type {session_type}')
            if (capital_limit := float(form_data['capital'])) > imarket.capital and session_type in [Session.Type.LIVE_SANDBOX, Session.Type.LIVE_MAINNET]:
                raise InsufficientBalance(f'Capital limit {capital_limit} is more than market capital {imarket.capital}')
            if (asset_limit := float(form_data['assets'])) > imarket.assets.get(symbol.base, 0) and session_type in [Session.Type.LIVE_SANDBOX, Session.Type.LIVE_MAINNET]:
                raise InsufficientBalance(f'Asset limit {asset_limit} is more than market assets {imarket.assets}')
            planned_shutdown = form_data.get('planned_shutdown', None)
            if planned_shutdown and not planned_shutdown > datetime.now(pytz.UTC):
                raise ValueError('Planned shutdown must be in the future')
            candle_source = form_data.get('candle_source', 'trade')
        except Exception as e:
            return render(request, 'session-init.html', {'markets': markets, 'form_error': repr(e)})
        try:
            ll = LiveLoop(
                symbol=symbol.name,
                market=market,
                strategy=get_strategy('v1')({
                    'source': form_data.get('source', 'close'),
                    'stochrsi': {'length': int(form_data.get('stoch_length', 3))},
                    'volume': {'ma': int(form_data.get('volume_ma', 20))},
                }),
                capital_limit=capital_limit,
                asset_limit=asset_limit,
                freq=form_data['freq'],
                end=planned_shutdown,
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
            return render(request, 'session-init.html', {'markets': markets, 'form_error': f'Cannot initiate session: {e!r}'})
        return redirect('session-detail', pk=ll.session.pk)



class SessionManageView(View):
    def post(self, request, pk):
        payload = request.POST
        session = Session.objects.get(pk=pk)
        action = payload['action']
        match action:
            case 'force_buy':
                pass
            case 'force_sell':
                pass
            case _:
                pass
        request.session['message'] = {
            'type': 'warning',
            'text': 'Action not implemented.'
        }
        return redirect('session-detail', pk=session.pk)


class SessionTerminateView(View):
    def get(self, request, pk):
        session = Session.objects.get(pk=pk)
        if not session.status in [Session.Status.ONGOING, Session.Status.PAUSED]:
            return render(request, 'session-detail.html', {'session': session, 'error': {
                'type': 'error',
                'text': 'Session is not ongoing.'
            }})
        session.status = Session.Status.COMPLETED
        session.ended = datetime.now(pytz.UTC)
        session.planned_shutdown = datetime.now(pytz.UTC)
        session.save()
        return redirect('session-detail', pk=session.pk)


class SessionPauseView(View):
    def get(self, request, pk):
        session = Session.objects.get(pk=pk)
        if not session.status == Session.Status.ONGOING:
            return render(request, 'session-detail.html', {'session': session, 'error': {
                'type': 'error',
                'text': 'Session is not ongoing.'
            }})
        session.status = Session.Status.PAUSED
        session.save()
        return redirect('session-detail', pk=session.pk)


class SessionResumeView(View):
    def get(self, request, pk):
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


class SessionUpdateView(View):
    def post(self, request, pk):
        session = Session.objects.get(pk=pk)
        print(request.POST)
        # Checkboxes are not included in POST data if they are unchecked,
        # so we explicitly check for their presence.
        if 'session_buy_enabled' in request.POST:
            session.buy_enabled = bool(int(request.POST.get('session_buy_enabled', 0)))
        if 'session_sell_enabled' in request.POST:
            session.sell_enabled = bool(int(request.POST.get('session_sell_enabled', 0)))
        if 'session_buy' in request.POST and float(request.POST.get('session_buy', 0)) > 0:
            iface = session.symbol.market.get_interface()
            amt = float(request.POST.get('session_buy'))
            order = iface.place_market_order(session.symbol.name, 'buy', funds=amt)
            order.force = True
            signal = Signal.objects.create(session=session, side='BUY', price=order.display_price, timestamp=datetime.now(pytz.UTC))
            order.signal = signal
            order.save()
            ts = datetime.now()
            while not order.status == Order.Status.FILLED and datetime.now() - ts < timedelta(seconds=10):
                order.refresh_from_market(iface)
            if not order.status == Order.Status.FILLED:
                request.session['error'] = {
                    'type': 'error',
                    'text': f'Order {order.oid} not filled. {order.status}'
                }
            else:
                session.capital -= order.deal_funds
                session.assets += order.deal_size
        if 'session_sell' in request.POST and float(request.POST.get('session_sell', 0)) > 0:
            iface = session.symbol.market.get_interface()
            amt = float(request.POST.get('session_sell'))
            order = iface.place_market_order(session.symbol.name, 'sell', quantity=amt)
            order.force = True
            signal = Signal.objects.create(session=session, side='SELL', price=order.display_price, timestamp=datetime.now(pytz.UTC))
            order.signal = signal
            order.save()
            ts = datetime.now()
            while not order.status == Order.Status.FILLED and datetime.now() - ts < timedelta(seconds=10):
                order.refresh_from_market(iface)
            if not order.status == Order.Status.FILLED:
                request.session['error'] = {
                    'type': 'error',
                    'text': f'Order {order.oid} not filled. {order.status}'
                }
            else:
                session.capital += order.deal_funds
                session.assets -= order.deal_size
        session.save()
        return redirect('session-detail', pk=session.pk)
      

class MarketListView(View):
    def get(self, request):
        markets = Market.objects.filter(trading_enabled=True, mainnet_enabled=True).order_by('exchange_name')
        return render(request, 'market-list.html', {'markets': markets})


class MarketDetailView(View):
    def get(self, request, pk):
        market = Market.objects.get(pk=pk)
        interface = market.get_interface()
        symbols = Symbol.objects.filter(market=market)
        return render(request, 'market-detail.html', {'market': market, 'symbols': symbols, 'interface': interface})
    

def raw_market_data(request, pk):
    market = Market.objects.get(pk=pk)
    return JsonResponse({
        'assets': json.loads(market.assets) if market.assets else {},
        'prices': json.loads(market.prices) if market.prices else {},
        'capital': market.usdt,
        'equity': market.equity,
        'updated': market.assets_updated_at,
        'available_capital': market.available_capital,
    })


class SearchSymbolView(View):
    def post(self, request):
        symbol = request.POST.get('symbol')
        query = Symbol.objects.filter(Q(name__icontains=symbol) | Q(market__name__icontains=symbol))
        return [symbol.name for symbol in query]


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
        return render(request, 'watchdog.html', context={'watchdog': watchdog()})


class OrderManagementView(View):
    def get(self, request):
        markets = Market.objects.filter(trading_enabled=True).order_by('exchange_name').order_by('exchange_name')
        return render(request, 'order-management.html', context={ 'markets': markets })
    
    def post(self, request):
        payload = request.POST
        market = Market.objects.get(pk=payload['market'])
        symbol_name = payload['symbol']
        symbol_name = symbol_name.upper().replace('-', '').replace('/', '').replace('USDT', '') + '-USDT'
        symbol = Symbol.objects.get(name=symbol_name, market=market)
        interface = market.get_interface()
        amount = float(payload['amount'])
        if payload['side'] == 'SELL':
            order = interface.place_market_order(symbol.name, 'sell', quantity=amount)
            return HttpResponse(f'Order {order.oid} placed. {order.details}')
        elif payload['side'] == 'BUY':
            order = interface.place_market_order(symbol.name, 'buy', quantity=amount)
            return HttpResponse(f'Order {order.oid} placed. {order.details}')
        return HttpResponse('Invalid side')


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
            symbol = symbol + '-USDT'

        market = Market.objects.get(pk=market_id)
        prices = json.loads(market.prices)
        if not symbol in prices:
            response['message'] = f'No price found for {symbol}'
            return JsonResponse(response)
        response['price'] = prices[symbol]
        response['updated'] = market.assets_updated_at
        return JsonResponse(response)
