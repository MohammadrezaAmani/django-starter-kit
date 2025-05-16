from django.urls import include, path, re_path
from rest_framework.routers import DefaultRouter

from .consumers import NotificationConsumer
from .views import (
    NotificationBatchViewSet,
    NotificationTemplateViewSet,
    NotificationViewSet,
    notification_list,
)

router = DefaultRouter()
router.register(
    r"templates", NotificationTemplateViewSet, basename="notification-template"
)
router.register(r"notifications", NotificationViewSet, basename="notification")
router.register(r"batches", NotificationBatchViewSet, basename="notification-batch")

urlpatterns = [
    # API endpoints
    path("api/", include(router.urls)),
    # Frontend view for in-app notifications
    path("", notification_list, name="notification_list"),
]

websocket_urlpatterns = [
    re_path(r"ws/notifications/$", NotificationConsumer.as_asgi()),
]
