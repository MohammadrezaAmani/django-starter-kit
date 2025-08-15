import logging

from django.contrib.auth import get_user_model
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from ...models import ActivityLog, Language
from ...permissions import IsOwnerOrAdmin, can_view_user_profile
from ...serializers import LanguageSerializer
from apps.accounts.views.user import UserRateThrottle
from apps.events.views import StandardResultsSetPagination

logger = logging.getLogger(__name__)
User = get_user_model()


class LanguageViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user language proficiencies.
    """

    serializer_class = LanguageSerializer
    pagination_class = StandardResultsSetPagination
    throttle_classes = [UserRateThrottle]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["proficiency", "is_native"]
    search_fields = ["name"]
    ordering_fields = ["name", "proficiency"]
    ordering = ["name"]

    def get_queryset(self):
        """Filter languages based on user and permissions."""
        if self.action == "list":
            # Get user from query params or current user
            user_id = self.request.query_params.get("user_id")
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                    if not can_view_user_profile(self.request.user, user):
                        raise PermissionDenied("Cannot view this user's languages")
                    return Language.objects.filter(user=user)
                except User.DoesNotExist:
                    return Language.objects.none()
            else:
                return Language.objects.filter(user=self.request.user)

        return Language.objects.filter(user=self.request.user)

    def get_permissions(self):
        if self.action in [
            "list",
            "retrieve",
            "by_proficiency",
            "native_languages",
            "proficiency_levels",
        ]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        """Create language for the current user."""
        language = serializer.save(user=self.request.user)

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Added language: {language.name} ({language.get_proficiency_display()})",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_update(self, serializer):
        """Update language and log activity."""
        language = serializer.save()

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Updated language: {language.name} ({language.get_proficiency_display()})",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_destroy(self, instance):
        """Delete language and log activity."""
        # Log activity before deletion
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Deleted language: {instance.name}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

        instance.delete()

    @extend_schema(
        tags=["Languages"],
        responses={200: LanguageSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        """List user languages with filtering and search."""
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error listing languages: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get languages"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Languages"],
        request=LanguageSerializer,
        responses={201: LanguageSerializer},
    )
    def create(self, request, *args, **kwargs):
        """Create a new language entry."""
        try:
            # Check if language already exists for this user
            language_name = request.data.get("name")
            if (
                language_name
                and Language.objects.filter(
                    user=request.user, name__iexact=language_name
                ).exists()
            ):
                return Response(
                    {"error": "Language already exists"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return super().create(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error creating language: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to create language"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Languages"],
        request=LanguageSerializer,
        responses={200: LanguageSerializer},
    )
    def update(self, request, *args, **kwargs):
        """Update a language entry."""
        try:
            return super().update(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error updating language: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to update language"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Languages"],
        responses={204: None},
    )
    def destroy(self, request, *args, **kwargs):
        """Delete a language entry."""
        try:
            return super().destroy(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error deleting language: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to delete language"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Languages"],
        responses={200: LanguageSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def by_proficiency(self, request):
        """Get languages by proficiency level."""
        try:
            proficiency = request.query_params.get("proficiency")
            if not proficiency:
                return Response(
                    {"error": "Proficiency parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            languages = self.get_queryset().filter(proficiency=proficiency)
            serializer = self.get_serializer(languages, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(
                f"Error getting languages by proficiency: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get languages by proficiency"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Languages"],
        responses={200: LanguageSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def native_languages(self, request):
        """Get native languages."""
        try:
            native_languages = self.get_queryset().filter(is_native=True)
            serializer = self.get_serializer(native_languages, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting native languages: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get native languages"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Languages"],
        responses={200: {"proficiency_levels": "list"}},
    )
    @action(detail=False, methods=["get"])
    def proficiency_levels(self, request):
        """Get available proficiency levels."""
        try:
            levels = [
                {"value": choice[0], "label": choice[1]}
                for choice in Language.Proficiency.choices
            ]
            return Response({"proficiency_levels": levels})
        except Exception as e:
            logger.error(f"Error getting proficiency levels: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get proficiency levels"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Languages"],
        responses={200: LanguageSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def fluent(self, request):
        """Get fluent and native languages."""
        try:
            fluent_languages = self.get_queryset().filter(
                proficiency__in=[
                    Language.Proficiency.FLUENT,
                    Language.Proficiency.NATIVE,
                ]
            )
            serializer = self.get_serializer(fluent_languages, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting fluent languages: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get fluent languages"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Languages"],
        responses={200: {"stats": "dict"}},
    )
    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Get language statistics."""
        try:
            queryset = self.get_queryset()
            total_languages = queryset.count()
            native_count = queryset.filter(is_native=True).count()

            proficiency_stats = {}
            for choice in Language.Proficiency.choices:
                count = queryset.filter(proficiency=choice[0]).count()
                proficiency_stats[choice[1]] = count

            stats = {
                "total_languages": total_languages,
                "native_languages": native_count,
                "proficiency_breakdown": proficiency_stats,
            }

            return Response({"stats": stats})
        except Exception as e:
            logger.error(f"Error getting language stats: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get language statistics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
