import threading
from datetime import datetime, timedelta

import pytz
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.views import View

from livetest import LiveLoop
from markets.errors import InsufficientBalance, MarketDisabledTrading, SymbolNotInMarket
from quantapi.models import (LiveLoopCache, Market, Order, Session, Signal,
                             Symbol)
from strategy import get_strategy


class HomeView(View):
    def get(self, request):
        sessions = Session.objects.order_by('-started')[:12]
        orders = Order.objects.all()[:5]
        signals = Signal.objects.all()[:5]
        total_profit = sum([session.profit() for session in sessions])
        return render(request, 'index.html', {
            'sessions': sessions, 
            'orders': orders, 
            'signals': signals, 
            'total_profit': total_profit,})


class SessionDetailView(View):
    def get(self, request, pk):
        session = Session.objects.get(pk=pk)
        signals = Signal.objects.filter(session=session)
        orders = Order.objects.filter(signal__in=signals)
        error = request.session.pop('error', None)
        market = session.symbol.market
        return render(request, 'session-detail.html', {'session': session, 'error': error, 'orders': orders, 'signals': signals, 'market': market})


class SessionListView(View):
    def get(self, request, query=None):
        if query is None:
            query = Session.objects.all()
        query = query.order_by('-started')
        paginator = Paginator(query, 20)
        page_number = request.GET.get('page')
        page = paginator.get_page(page_number)
        markets = Market.objects.all()
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
        markets = Market.objects.all()
        return render(request, 'session-init.html', {'markets': markets})

    def post(self, request, *args, **kwargs):
        form_data = request.POST
        markets = Market.objects.all()
        try:
            market = Market.objects.get(pk=form_data['market'])
            imarket = market.get_interface()
            if not imarket.has_symbol(form_data['symbol']):
                raise SymbolNotInMarket(f'Symbol {form_data["symbol"]} not found in market {market.exchange_name}')
            symbol = Symbol.objects.get_or_create(name=form_data['symbol'], market=market)[0]
            if not Session.is_valid_freq((freq := form_data['freq'])):
                raise ValueError(f'Invalid frequency {freq}')
            if not market.is_valid_session_type((session_type := form_data['type'])):
                raise MarketDisabledTrading(f'Market {market.exchange_name} does not support session type {session_type}')
            if (capital_limit := float(form_data['capital'])) > imarket.capital:
                raise InsufficientBalance(f'Capital limit {capital_limit} is more than market capital {imarket.capital}')
            if (asset_limit := float(form_data['assets'])) > imarket.assets.get(symbol.name, 0):
                raise InsufficientBalance(f'Asset limit {asset_limit} is more than market assets {imarket.assets}')
            planned_shutdown = form_data.get('planned_shutdown', None)
            if not planned_shutdown > datetime.now(pytz.UTC):
                raise ValueError('Planned shutdown must be in the future')
        except Market.DoesNotExist:
            return render(request, 'session-init.html', {'markets': markets, 'form_error': f'Market with id={form_data["market"]} does not exist.'})
        except InsufficientBalance as e:
            return render(request, 'session-init.html', {'markets': markets, 'form_error': repr(e)})
        except SymbolNotInMarket as e:
            return render(request, 'session-init.html', {'markets': markets, 'form_error': repr(e)})
        except MarketDisabledTrading as e:
            return render(request, 'session-init.html', {'markets': markets, 'form_error': repr(e)})
        except ValueError as e:
            return render(request, 'session-init.html', {'markets': markets, 'form_error': repr(e)})
        try:
            ll = LiveLoop(
                symbol=symbol.name,
                market=market.get_interface(),
                strategy=get_strategy('v1')(),
                capital_limit=capital_limit,
                asset_limit=asset_limit,
                freq=freq,
                end=planned_shutdown,
                market_id_for_symbol=market.pk,
            )
            ll.run()
            cache = LiveLoopCache(
                session=ll.session,
                status='INIT',
                created=datetime.now(pytz.UTC),
                last_started=datetime.now(pytz.UTC),
                thread_id=ll.thread.ident if ll.thread else None,
            )
            cache.save()
        except Exception as e:
            return render(request, 'session-init.html', {'markets': markets, 'form_error': f'Cannot initiate session: {e!r}'})
        return redirect('session-detail', pk=ll.session.pk)


class SessionTerminateView(View):
    def get(self, request, pk):
        session = Session.objects.get(pk=pk)
        if not session.status == Session.Status.ONGOING:
            return render(request, 'session-detail.html', {'session': session, 'error': {
                'type': 'error',
                'text': 'Session is not ongoing.'
            }})
        session.status = Session.Status.CANCELLED
        session.save()
        return redirect('session-detail', pk=session.pk)


class MarketListView(View):
    def get(self, request):
        markets = Market.objects.all()
        return render(request, 'market-list.html', {'markets': markets})


class SearchSymbolView(View):
    def post(self, request):
        symbol = request.POST.get('symbol')
        query = Symbol.objects.filter(Q(name__icontains=symbol) | Q(market__name__icontains=symbol))
        return [symbol.name for symbol in query]


class RunningThreadsView(View):
    def get(self, request):
        threads = threading.enumerate()
        return render(request, 'threads.html', {'threads': threads})
