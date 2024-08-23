# myapp/routing.py
from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/orderbook/', consumers.OrderbookConsumer.as_asgi()),
    path('ws/candles/<str:market>/<str:symbol>/', consumers.CandleConsumer.as_asgi()),
]
