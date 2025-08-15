import logging

from django.contrib.auth import get_user_model
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from ...models import ActivityLog, Experience
from ...permissions import IsOwnerOrAdmin, can_view_user_profile
from ...serializers import ExperienceSerializer
from apps.accounts.views.user import UserRateThrottle
from apps.events.views import StandardResultsSetPagination

logger = logging.getLogger(__name__)
User = get_user_model()


class ExperienceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user work experience.
    """

    serializer_class = ExperienceSerializer
    pagination_class = StandardResultsSetPagination
    throttle_classes = [UserRateThrottle]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["type", "is_current", "company"]
    search_fields = ["title", "company", "description"]
    ordering_fields = ["start_date", "end_date", "company", "title"]
    ordering = ["-start_date"]

    def get_queryset(self):
        """Filter experience based on user and permissions."""
        if self.action == "list":
            # Get user from query params or current user
            user_id = self.request.query_params.get("user_id")
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                    if not can_view_user_profile(self.request.user, user):
                        raise PermissionDenied("Cannot view this user's experience")
                    return Experience.objects.filter(user=user)
                except User.DoesNotExist:
                    return Experience.objects.none()
            else:
                return Experience.objects.filter(user=self.request.user)

        return Experience.objects.filter(user=self.request.user)

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        """Create experience for the current user."""
        experience = serializer.save(user=self.request.user)

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Added experience: {experience.title} at {experience.company}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_update(self, serializer):
        """Update experience and log activity."""
        experience = serializer.save()

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Updated experience: {experience.title} at {experience.company}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_destroy(self, instance):
        """Delete experience and log activity."""
        # Log activity before deletion
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Deleted experience: {instance.title} at {instance.company}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

        instance.delete()

    @extend_schema(
        tags=["Experience"],
        responses={200: ExperienceSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        """List user experiences with filtering and search."""
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error listing experiences: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get experiences"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Experience"],
        request=ExperienceSerializer,
        responses={201: ExperienceSerializer},
    )
    def create(self, request, *args, **kwargs):
        """Create a new experience entry."""
        try:
            # Validate that if is_current is True, no end_date should be provided
            if request.data.get("is_current") and request.data.get("end_date"):
                return Response(
                    {"error": "Current positions cannot have an end date"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return super().create(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error creating experience: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to create experience"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Experience"],
        request=ExperienceSerializer,
        responses={200: ExperienceSerializer},
    )
    def update(self, request, *args, **kwargs):
        """Update an experience entry."""
        try:
            # Validate that if is_current is True, no end_date should be provided
            if request.data.get("is_current") and request.data.get("end_date"):
                return Response(
                    {"error": "Current positions cannot have an end date"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return super().update(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error updating experience: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to update experience"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Experience"],
        responses={204: None},
    )
    def destroy(self, request, *args, **kwargs):
        """Delete an experience entry."""
        try:
            return super().destroy(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error deleting experience: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to delete experience"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Experience"],
        responses={200: ExperienceSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def current(self, request):
        """Get current work positions."""
        try:
            current_experiences = self.get_queryset().filter(is_current=True)
            serializer = self.get_serializer(current_experiences, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting current experiences: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get current experiences"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Experience"],
        responses={200: ExperienceSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def by_company(self, request):
        """Get experiences grouped by company."""
        try:
            company = request.query_params.get("company")
            if not company:
                return Response(
                    {"error": "Company parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            experiences = self.get_queryset().filter(company__icontains=company)
            serializer = self.get_serializer(experiences, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(
                f"Error getting experiences by company: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get experiences by company"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Experience"],
        responses={200: ExperienceSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def by_type(self, request):
        """Get experiences by type (work, internship, volunteer, freelance)."""
        try:
            experience_type = request.query_params.get("type")
            if not experience_type:
                return Response(
                    {"error": "Type parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            experiences = self.get_queryset().filter(type=experience_type)
            serializer = self.get_serializer(experiences, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting experiences by type: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get experiences by type"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
