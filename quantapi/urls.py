from django.urls import include, path
from rest_framework import routers

from quantapi.viewsets import (GlobalSymbolViewSet, GroupOrderViewSet, IssueViewSet, MarketAccountViewSet, MarketSymbolViewSet,
                               MarketViewSet, NotificationViewSet, OrderViewSet, SessionGroupViewSet, SessionViewSet, SignalViewSet, StrategyViewSet)


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
router.register(r'notifications', NotificationViewSet)
router.register(r'issues', IssueViewSet)


urlpatterns = [
    path('', include(router.urls))
]