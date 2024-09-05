from django.urls import path
import orderpulse.consumers as consumers

websocket_urlpatterns = [
    path('ws/ticker/<str:market>/<str:symbol>/', consumers.TickerConsumer.as_asgi()),
    path('ws/miniorderbook/<str:market>/<str:symbol>/', consumers.MiniOrderbookConsumer.as_asgi()),
]
