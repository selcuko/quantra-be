from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.conf.urls.static import static
from quantapi.views import BacktestInitView, BacktestResultView, CoinScanView, FavoritesView, HomeView, MarketDetailView, MarketListView, OrderManagementView, PriceView, RunningThreadsView, \
    SessionInitView, SessionListView, SessionUpdateView,SessionDetailView, SymbolView, WatchdogView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', HomeView.as_view(), name='home'),
    path('sessions/', SessionListView.as_view(), name='session-list'),
    path('session/init/', SessionInitView.as_view(), name='session-init'),
    path('session/<int:pk>/', SessionDetailView.as_view(), name='session-detail'),
    path('session/<int:pk>/terminate/', SessionUpdateView.terminate, name='session-terminate'),
    path('session/<int:pk>/pause/', SessionUpdateView.pause, name='session-pause'),
    path('session/<int:pk>/resume/', SessionUpdateView.resume, name='session-resume'),
    path('session/<int:pk>/update/', SessionUpdateView.as_view(), name='session-update'),
    path('markets/', MarketListView.as_view(), name='market-list'),
    path('market/<int:pk>/', MarketDetailView.as_view(), name='market-detail'),
    path('market/<int:pk>/raw/', MarketDetailView.raw, name='market-raw'),
    path('threads/', RunningThreadsView.as_view(), name='running-threads'),
    path('backtest/init/', BacktestInitView.as_view(), name='backtest-init'),
    path('backtest/<int:pk>/', BacktestResultView.as_view(), name='backtest-result'),
    path('watchdog/', WatchdogView.as_view(), name='watchdog'),
    path('orders/', OrderManagementView.as_view(), name='order-management'),
    path('price/', PriceView.as_view(), name='price'),
    path('symbol/<slug:cid>/', SymbolView.as_view(), name='symbol-detail'),
    path('coinscan/', CoinScanView.as_view(), name='symbol-scan'),
    path('favorites/', FavoritesView.as_view(), name='symbol-favorites'),
    path('favorites/modify/', FavoritesView.favorite, name='symbol-favorite-modify')
]
urlpatterns += [path('silk/', include('silk.urls', namespace='silk'))]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
