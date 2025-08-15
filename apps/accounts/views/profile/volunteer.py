import logging

from django.contrib.auth import get_user_model
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from ...models import ActivityLog, Volunteer
from ...permissions import IsOwnerOrAdmin, can_view_user_profile
from ...serializers import VolunteerSerializer
from apps.accounts.views.user import UserRateThrottle
from apps.events.views import StandardResultsSetPagination

logger = logging.getLogger(__name__)
User = get_user_model()


class VolunteerViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user volunteer experiences.
    """

    serializer_class = VolunteerSerializer
    pagination_class = StandardResultsSetPagination
    throttle_classes = [UserRateThrottle]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["organization", "is_current"]
    search_fields = ["role", "organization", "description", "cause"]
    ordering_fields = ["start_date", "end_date", "organization", "role"]
    ordering = ["-start_date"]

    def get_queryset(self):
        """Filter volunteer experiences based on user and permissions."""
        if self.action == "list":
            # Get user from query params or current user
            user_id = self.request.query_params.get("user_id")
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                    if not can_view_user_profile(self.request.user, user):
                        raise PermissionDenied(
                            "Cannot view this user's volunteer experience"
                        )
                    return Volunteer.objects.filter(user=user)
                except User.DoesNotExist:
                    return Volunteer.objects.none()
            else:
                return Volunteer.objects.filter(user=self.request.user)

        return Volunteer.objects.filter(user=self.request.user)

    def get_permissions(self):
        if self.action in [
            "list",
            "retrieve",
            "current",
            "by_organization",
            "by_cause",
            "recent",
        ]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        """Create volunteer experience for the current user."""
        volunteer = serializer.save(user=self.request.user)

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Added volunteer experience: {volunteer.role} at {volunteer.organization}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_update(self, serializer):
        """Update volunteer experience and log activity."""
        volunteer = serializer.save()

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Updated volunteer experience: {volunteer.role} at {volunteer.organization}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_destroy(self, instance):
        """Delete volunteer experience and log activity."""
        # Log activity before deletion
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Deleted volunteer experience: {instance.role} at {instance.organization}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

        instance.delete()

    @extend_schema(
        tags=["Volunteer"],
        responses={200: VolunteerSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        """List user volunteer experiences with filtering and search."""
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            logger.error(
                f"Error listing volunteer experiences: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get volunteer experiences"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Volunteer"],
        request=VolunteerSerializer,
        responses={201: VolunteerSerializer},
    )
    def create(self, request, *args, **kwargs):
        """Create a new volunteer experience entry."""
        try:
            # Validate that if is_current is True, no end_date should be provided
            if request.data.get("is_current") and request.data.get("end_date"):
                return Response(
                    {"error": "Current volunteer positions cannot have an end date"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return super().create(request, *args, **kwargs)
        except Exception as e:
            logger.error(
                f"Error creating volunteer experience: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to create volunteer experience"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Volunteer"],
        request=VolunteerSerializer,
        responses={200: VolunteerSerializer},
    )
    def update(self, request, *args, **kwargs):
        """Update a volunteer experience entry."""
        try:
            # Validate that if is_current is True, no end_date should be provided
            if request.data.get("is_current") and request.data.get("end_date"):
                return Response(
                    {"error": "Current volunteer positions cannot have an end date"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return super().update(request, *args, **kwargs)
        except Exception as e:
            logger.error(
                f"Error updating volunteer experience: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to update volunteer experience"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Volunteer"],
        responses={204: None},
    )
    def destroy(self, request, *args, **kwargs):
        """Delete a volunteer experience entry."""
        try:
            return super().destroy(request, *args, **kwargs)
        except Exception as e:
            logger.error(
                f"Error deleting volunteer experience: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to delete volunteer experience"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Volunteer"],
        responses={200: VolunteerSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def current(self, request):
        """Get current volunteer positions."""
        try:
            current_volunteer = self.get_queryset().filter(is_current=True)
            serializer = self.get_serializer(current_volunteer, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(
                f"Error getting current volunteer experiences: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get current volunteer experiences"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Volunteer"],
        responses={200: VolunteerSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def by_organization(self, request):
        """Get volunteer experiences by organization."""
        try:
            organization = request.query_params.get("organization")
            if not organization:
                return Response(
                    {"error": "Organization parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            volunteer_experiences = self.get_queryset().filter(
                organization__icontains=organization
            )
            serializer = self.get_serializer(volunteer_experiences, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(
                f"Error getting volunteer experiences by organization: {str(e)}",
                exc_info=True,
            )
            return Response(
                {"error": "Failed to get volunteer experiences by organization"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Volunteer"],
        responses={200: VolunteerSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def by_cause(self, request):
        """Get volunteer experiences by cause."""
        try:
            cause = request.query_params.get("cause")
            if not cause:
                return Response(
                    {"error": "Cause parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            volunteer_experiences = self.get_queryset().filter(cause__icontains=cause)
            serializer = self.get_serializer(volunteer_experiences, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(
                f"Error getting volunteer experiences by cause: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get volunteer experiences by cause"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Volunteer"],
        responses={200: VolunteerSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def recent(self, request):
        """Get recent volunteer experiences (last 3 years)."""
        try:
            from datetime import timedelta

            from django.utils import timezone

            three_years_ago = timezone.now().date() - timedelta(days=1095)
            recent_volunteer = self.get_queryset().filter(
                start_date__gte=three_years_ago
            )
            serializer = self.get_serializer(recent_volunteer, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(
                f"Error getting recent volunteer experiences: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get recent volunteer experiences"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Volunteer"],
        responses={200: {"stats": "dict"}},
    )
    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Get volunteer experience statistics."""
        try:
            queryset = self.get_queryset()
            total_experiences = queryset.count()
            current_count = queryset.filter(is_current=True).count()

            # Calculate total volunteer time
            total_hours = 0
            for volunteer in queryset:
                if volunteer.hours_per_week and volunteer.start_date:
                    end_date = volunteer.end_date or timezone.now().date()
                    weeks = (end_date - volunteer.start_date).days // 7
                    total_hours += volunteer.hours_per_week * weeks

            # Get top organizations
            from django.db.models import Count

            top_orgs = (
                queryset.values("organization")
                .annotate(count=Count("organization"))
                .order_by("-count")[:5]
            )

            stats = {
                "total_experiences": total_experiences,
                "current_experiences": current_count,
                "estimated_total_hours": total_hours,
                "top_organizations": list(top_orgs),
            }

            return Response({"stats": stats})
        except Exception as e:
            logger.error(f"Error getting volunteer stats: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get volunteer statistics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
