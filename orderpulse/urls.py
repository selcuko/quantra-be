from django.urls import path

from orderpulse.views import chat_index, room

urlpatterns = [
    path('', chat_index),
    path('chat/<str:room_name>/', room),
]