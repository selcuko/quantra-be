from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.conf.urls.static import static
from quantapi.views import BacktestInitView, BacktestResultView, CoinScanView, FavoritesView, HomeView, IssueDetailView, MarketDetailView, MarketListView, NotificationDetailView, NotificationsView, OrderBookView, OrderManagementView, PriceView, RunningThreadsView, SessionGroupDetailView, SessionGroupInitView, SessionGroupListView, \
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
    path('sessiongroups/', SessionGroupListView.as_view(), name='sessiongroup-list'),
    path('sessiongroup/init/', SessionGroupInitView.as_view(), name='sessiongroup-init'),
    path('sessiongroup/<int:pk>/', SessionGroupDetailView.as_view(), name='sessiongroup-detail'),
    path('sessiongroup/<int:pk>/init/', SessionGroupDetailView.init, name='sessiongroup-detail-init'),
    path('sessiongroup/<int:pk>/update/', SessionGroupDetailView.update, name='sessiongroup-update'),
    path('sessiongroup/<int:pk>/pause/', SessionGroupDetailView.pause, name='sessiongroup-pause'),
    path('sessiongroup/<int:pk>/resume/', SessionGroupDetailView.resume, name='sessiongroup-resume'),
    path('sessiongroup/<int:pk>/terminate/', SessionGroupDetailView.terminate, name='sessiongroup-terminate'),
    path('sessiongroup/<int:pk>/issues/', SessionGroupDetailView.issues, name='sessiongroup-issues'),
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
    path('symbols/search/', OrderBookView.search, name='symbol-search'),
    path('coinscan/', CoinScanView.as_view(), name='symbol-scan'),
    path('favorites/', FavoritesView.as_view(), name='symbol-favorites'),
    path('favorites/modify/', FavoritesView.favorite, name='symbol-favorite-modify'),
    path('orderbook/', OrderBookView.as_view(), name='orderbook'),
    path('notifications/', NotificationsView.as_view(), name='notification-list'),
    path('notifications/<int:pk>/', NotificationDetailView.as_view(), name='notification-detail'),
    path('notifications/<int:pk>/acknowledge/', NotificationDetailView.acknowledge, name='notification-acknowledge'),
    path('issue/<slug:object_type>/<int:object_id>/', IssueDetailView.for_object, name='issue-forobject'),
    path('issue/<int:pk>/', IssueDetailView.as_view(), name='issue-detail'),
]
urlpatterns += [path('silk/', include('silk.urls', namespace='silk'))]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
