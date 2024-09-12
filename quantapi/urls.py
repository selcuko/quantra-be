from django.urls import include, path
from rest_framework import routers

from quantapi.viewsets import (CandlesViewSet, ContactFormViewSet, GlobalSymbolViewSet, GroupOrderViewSet, MarketAccountViewSet, MarketSymbolViewSet,
                               MarketViewSet, OrderViewSet, KeeperView, SessionGroupViewSet, SessionViewSet, SignalViewSet, StrategyViewSet, TagViewSet)


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
router.register(r'contactforms', ContactFormViewSet)
router.register(r'tags', TagViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('candles/<str:market>/<str:symbol>/<str:interval>/', CandlesViewSet.as_view({'get': 'get'})),
    path('keepers/', KeeperView.as_view({'get': 'list'})),
    path('agg/', include('orderpulse.urls')),
]