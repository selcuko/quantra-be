from django.urls import include, path
from rest_framework import routers

from quantapi.viewsets import (CandlesViewSet, ContactFormViewSet, GlobalSymbolViewSet, GroupOrderViewSet, HealthViewSet, LiveLoopViewSet, LoopGroupViewSet, MarketAccountViewSet, MarketSymbolViewSet,
                               MarketViewSet, OrderViewSet, KeeperView, SessionGroupViewSet, SessionViewSet, SignalViewSet, StrategyViewSet, TagViewSet, ThreadViewSet)


router = routers.DefaultRouter()
router.register(r'markets', MarketViewSet)
router.register(r'accounts', MarketAccountViewSet)
router.register(r'marketsymbols', MarketSymbolViewSet)
router.register(r'globalsymbols', GlobalSymbolViewSet)
router.register(r'strategies', StrategyViewSet)
router.register(r'sessions', SessionViewSet)
router.register(r'sessiongroups', SessionGroupViewSet)
router.register(r'orders', OrderViewSet)
router.register(r'grouporders', GroupOrderViewSet)
router.register(r'signals', SignalViewSet)
router.register(r'liveloops', LiveLoopViewSet, basename='liveloops')
router.register(r'loopgroups', LoopGroupViewSet, basename='loopgroups')
router.register(r'threads', ThreadViewSet, basename='threads')
router.register(r'health', HealthViewSet, basename='health')
router.register(r'contactforms', ContactFormViewSet)
router.register(r'tags', TagViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('candles/<str:market>/<str:symbol>/<str:interval>/', CandlesViewSet.as_view({'get': 'get'})),
    path('keepers/', KeeperView.as_view({'get': 'list'})),
    path('agg/', include('orderpulse.urls')),
]