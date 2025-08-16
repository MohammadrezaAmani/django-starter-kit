from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

# statics and medias
from django.conf.urls.static import static

urlpatterns = (
    [
        path("admin/", admin.site.urls),
        path("accounts/", include("apps.accounts.urls")),
        path("", include("apps.chats.urls")),
        path("notifications/", include("apps.notifications.urls")),
        path("logs/", include("apps.audit_log.urls")),
        path("payment/", include("apps.payment.urls")),
        path("c/", include("apps.common.urls")),
        path("schema/", SpectacularAPIView.as_view(), name="schema"),
        path(
            "docs/",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="swagger-ui",
        ),
        path("redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
        path("feedback/", include("apps.feedback.urls")),
        path("silk/", include("silk.urls", namespace="silk")),
        path("events/", include("apps.events.urls", namespace="events")),
    ]
    + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
)

if settings.DEBUG:
    import debug_toolbar

    urlpatterns += [
        path("__debug__/", include(debug_toolbar.urls)),
    ]
