from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    EventCategoryViewSet,
    EventTagViewSet,
    EventViewSet,
    ExhibitorViewSet,
    ParticipantViewSet,
    ProductViewSet,
    SessionViewSet,
)

app_name = "events"

router = DefaultRouter()
router.register(r"", EventViewSet, basename="event")
router.register(r"categories", EventCategoryViewSet, basename="eventcategory")
router.register(r"tags", EventTagViewSet, basename="eventtag")
router.register(r"sessions", SessionViewSet, basename="session")
router.register(r"participants", ParticipantViewSet, basename="participant")
router.register(r"exhibitors", ExhibitorViewSet, basename="exhibitor")
router.register(r"products", ProductViewSet, basename="product")

urlpatterns = [
    path("", include(router.urls)),
]
