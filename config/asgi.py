import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application
from django.urls import re_path

from apps.chats.consumers import ChatConsumer, NotificationConsumer
from apps.notifications.urls import (
    websocket_urlpatterns as notifications_websocket_urlpatterns,
)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Chat WebSocket URL patterns
chat_websocket_urlpatterns = [
    re_path(r"ws/chat/$", ChatConsumer.as_asgi()),
    re_path(r"ws/chat/(?P<chat_id>[0-9a-f-]+)/$", ChatConsumer.as_asgi()),
    re_path(r"ws/notifications/$", NotificationConsumer.as_asgi()),
]

# Combine all WebSocket URL patterns
all_websocket_urlpatterns = (
    notifications_websocket_urlpatterns + chat_websocket_urlpatterns
)

application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(URLRouter(all_websocket_urlpatterns))
        ),
    }
)
