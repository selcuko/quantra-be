# myapp/routing.py
from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/orderbook/<str:market>/<str:symbol>/', consumers.OrderbookConsumer.as_asgi()),
    path('ws/miniorderbook/<str:market>/<str:symbol>/', consumers.MiniOrderbookConsumer.as_asgi()),
    path('ws/miniagg/<str:symbol>/<str:markets>/', consumers.MiniAggregatorConsumer.as_asgi()),
    path('ws/candles/<str:market>/<str:symbol>/',   consumers.CandleConsumer.as_asgi()),
]
