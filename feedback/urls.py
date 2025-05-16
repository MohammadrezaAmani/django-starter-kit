from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import FeedbackViewSet

router = DefaultRouter()
router.register(r"feedback", FeedbackViewSet, basename="feedback")

urlpatterns = [
    path("api/", include(router.urls)),
]
