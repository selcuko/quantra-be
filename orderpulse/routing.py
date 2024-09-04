# myapp/routing.py
from django.urls import path
import orderpulse.consumers as consumers

websocket_urlpatterns = [
    #path('ws/echo/', consumers_old.BasicConsumer.as_asgi()),
    #path('ws/orderbook/<str:market>/<str:symbol>/', consumers_old.OrderbookConsumer.as_asgi()),
    path('ws/miniorderbook/<str:market>/<str:symbol>/', consumers.MiniOrderbookConsumer.as_asgi()),
    #path('ws/miniagg/<str:symbol>/<str:markets>/', consumers_old.MiniAggregatorConsumer.as_asgi()),
    #path('ws/candles/<str:market>/<str:symbol>/',   consumers_old.CandleConsumer.as_asgi()),
]
