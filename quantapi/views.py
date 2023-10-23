from django.shortcuts import render
from django.views import View
from quantapi.models import Session, Order, Signal

class HomeView(View):
    def get(self, request):
        sessions = Session.objects.all()
        orders = Order.objects.all()
        signals = Signal.objects.all()
        total_profit = sum([session.profit() for session in sessions])
        return render(request, 'index.html', {'sessions': sessions, 'orders': orders, 'signals': signals, 'total_profit': total_profit})
