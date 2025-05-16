from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views.auth import (
    ForgotPasswordView,
    LoginView,
    LogoutView,
    MeView,
    RefreshView,
    RegisterView,
    ResetPasswordView,
    VerifyView,
)
from .views.user import UserViewSet

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")

urlpatterns = [
    path("api/auth/login/", LoginView.as_view(), name="login"),
    path("api/auth/logout/", LogoutView.as_view(), name="logout"),
    path("api/auth/me/", MeView.as_view(), name="me"),
    path("api/auth/refresh/", RefreshView.as_view(), name="refresh"),
    path("api/auth/verify/", VerifyView.as_view(), name="verify"),
    path("api/auth/register/", RegisterView.as_view(), name="register"),
    path(
        "api/auth/forgot-password/",
        ForgotPasswordView.as_view(),
        name="forgot-password",
    ),
    path(
        "api/auth/reset-password/", ResetPasswordView.as_view(), name="reset-password"
    ),
    # Include router URLs for UserViewSet
    path("api/", include(router.urls)),
]
