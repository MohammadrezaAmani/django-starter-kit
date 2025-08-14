from django.urls import include, path
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
from .views.profile import (
    AchievementViewSet,
    CertificationViewSet,
    EducationViewSet,
    ExperienceViewSet,
    LanguageViewSet,
    NetworkViewSet,
    ProjectViewSet,
    PublicationViewSet,
    RecommendationViewSet,
    ResumeViewSet,
    SkillViewSet,
    TaskViewSet,
    VolunteerViewSet,
)
from .views.user import UserViewSet

# Main router for core functionality
router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")

# Profile router for profile-related endpoints
profile_router = DefaultRouter()
profile_router.register(r"experience", ExperienceViewSet, basename="experience")
profile_router.register(r"education", EducationViewSet, basename="education")
profile_router.register(
    r"certifications", CertificationViewSet, basename="certification"
)
profile_router.register(r"projects", ProjectViewSet, basename="project")
profile_router.register(r"skills", SkillViewSet, basename="skill")
profile_router.register(r"languages", LanguageViewSet, basename="language")
profile_router.register(r"achievements", AchievementViewSet, basename="achievement")
profile_router.register(r"publications", PublicationViewSet, basename="publication")
profile_router.register(r"volunteer", VolunteerViewSet, basename="volunteer")
profile_router.register(r"networks", NetworkViewSet, basename="network")
profile_router.register(
    r"recommendations", RecommendationViewSet, basename="recommendation"
)
profile_router.register(r"tasks", TaskViewSet, basename="task")
profile_router.register(r"resumes", ResumeViewSet, basename="resume")

# Authentication and core URLs
urlpatterns = [
    # Authentication endpoints
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("refresh/", RefreshView.as_view(), name="refresh"),
    path("verify/", VerifyView.as_view(), name="verify"),
    path("register/", RegisterView.as_view(), name="register"),
    path(
        "forgot-password/",
        ForgotPasswordView.as_view(),
        name="forgot-password",
    ),
    path("reset-password/", ResetPasswordView.as_view(), name="reset-password"),
    # Profile endpoints under /profile/ namespace
    path("profile/", include(profile_router.urls)),
]

# Add main router URLs
urlpatterns.extend(router.urls)
