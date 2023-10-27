from datetime import datetime, timedelta

import pytz
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.views import View

from quantapi.forms import SessionInitForm
from quantapi.models import Market, Order, Session, Signal


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
        if request.session['session-list-time'] in time_map:
            sessions_from = datetime.now(pytz.UTC) - time_map.get(request.session['session-list-time'])
            query = query.filter(started__gte=datetime.now(pytz.UTC) - time_map.get(request.session['session-list-time']))
        else:
            request.session['message'] = {
                'type': 'error',
                'text': f'Invalid time range: {request.session["session-list-time"]}'
            }
        return self.get(request, query=query)



class SessionInitView(View):
    def get(self, request):
        form = SessionInitForm()
        return render(request, 'session-init.html', {'form': form})
    def post(self, request, *args, **kwargs):
        form = SessionInitForm(request.POST)
        if form.is_valid():
            session = form.save()
            return redirect('session-detail', pk=session.pk)
        else:
            return render(request, 'session-init.html', {'form': form})


class SessionTerminateView(View):
    def post(self, request, pk):
        session = Session.objects.get(pk=pk)
        if not session.status == Session.Status.ONGOING:
            request.session['message'] = {
                'type': 'error',
                'text': 'Session is not ongoing.'
            }
            return redirect('session-detail', pk=session.pk)
        session.status = Session.Status.CANCELLED
        session.save()
        return redirect('session-detail', pk=session.pk)


class MarketListView(View):
    def get(self, request):
        markets = Market.objects.all()
        return render(request, 'market-list.html', {'markets': markets})
