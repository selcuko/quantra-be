"""
URL configuration for quant project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.urls import path
from django.conf.urls.static import static
from quantapi.views import HomeView, MarketDetailView, MarketListView, RunningThreadsView, \
    SessionInitView, SessionListView, SessionManageView, SessionTerminateView, SessionDetailView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', HomeView.as_view(), name='home'),
    path('sessions/', SessionListView.as_view(), name='session-list'),
    path('session/<int:pk>/', SessionDetailView.as_view(), name='session-detail'),
    path('session/init/', SessionInitView.as_view(), name='session-init'),
    path('session/<int:pk>/terminate/', SessionTerminateView.as_view(), name='session-terminate'),
    path('session/<int:pk>/manage/', SessionManageView.as_view(), name='session-manage'),
    path('markets/', MarketListView.as_view(), name='market-list'),
    path('market/<int:pk>/', MarketDetailView.as_view(), name='market-detail'),
    path('threads/', RunningThreadsView.as_view(), name='running-threads'),
]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
