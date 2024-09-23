"""
ASGI config for quant project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

"""
ASGI config for quant project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'quant.settings')
asgi_app = get_asgi_application()
import orderpulse.routing
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

application = ProtocolTypeRouter({
    "http": asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            orderpulse.routing.websocket_urlpatterns
        )
    ),
})

