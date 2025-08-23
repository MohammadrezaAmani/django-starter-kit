import logging

from django.contrib.auth import get_user_model
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.accounts.views.user import UserRateThrottle
from apps.events.views import StandardResultsSetPagination

from ...models import ActivityLog, Education
from ...permissions import IsOwnerOrAdmin, can_view_user_profile
from ...serializers import EducationSerializer

logger = logging.getLogger(__name__)
User = get_user_model()


class EducationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user education background.
    """

    serializer_class = EducationSerializer
    pagination_class = StandardResultsSetPagination
    throttle_classes = [UserRateThrottle]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["is_current", "degree", "institution"]
    search_fields = ["institution", "degree", "field_of_study", "description"]
    ordering_fields = ["start_date", "end_date", "institution", "degree"]
    ordering = ["-start_date"]

    def get_queryset(self):
        """Filter education based on user and permissions."""
        if self.action == "list":
            # Get user from query params or current user
            user_id = self.request.query_params.get("user_id")
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                    if not can_view_user_profile(self.request.user, user):
                        raise PermissionDenied("Cannot view this user's education")
                    return Education.objects.filter(user=user)
                except User.DoesNotExist:
                    return Education.objects.none()
            else:
                return Education.objects.filter(user=self.request.user)

        return Education.objects.filter(user=self.request.user)

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        """Create education for the current user."""
        education = serializer.save(user=self.request.user)

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Added education: {education.degree} at {education.institution}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_update(self, serializer):
        """Update education and log activity."""
        education = serializer.save()

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Updated education: {education.degree} at {education.institution}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_destroy(self, instance):
        """Delete education and log activity."""
        # Log activity before deletion
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Deleted education: {instance.degree} at {instance.institution}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

        instance.delete()

    @extend_schema(
        tags=["Education"],
        responses={200: EducationSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        """List user education with filtering and search."""
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error listing education: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get education"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Education"],
        request=EducationSerializer,
        responses={201: EducationSerializer},
    )
    def create(self, request, *args, **kwargs):
        """Create a new education entry."""
        try:
            # Validate that if is_current is True, no end_date should be provided
            if request.data.get("is_current") and request.data.get("end_date"):
                return Response(
                    {"error": "Current education cannot have an end date"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return super().create(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error creating education: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to create education"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Education"],
        request=EducationSerializer,
        responses={200: EducationSerializer},
    )
    def update(self, request, *args, **kwargs):
        """Update an education entry."""
        try:
            # Validate that if is_current is True, no end_date should be provided
            if request.data.get("is_current") and request.data.get("end_date"):
                return Response(
                    {"error": "Current education cannot have an end date"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return super().update(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error updating education: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to update education"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Education"],
        responses={204: None},
    )
    def destroy(self, request, *args, **kwargs):
        """Delete an education entry."""
        try:
            return super().destroy(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error deleting education: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to delete education"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Education"],
        responses={200: EducationSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def current(self, request):
        """Get current education (ongoing studies)."""
        try:
            current_education = self.get_queryset().filter(is_current=True)
            serializer = self.get_serializer(current_education, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting current education: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get current education"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Education"],
        responses={200: EducationSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def by_institution(self, request):
        """Get education entries by institution."""
        try:
            institution = request.query_params.get("institution")
            if not institution:
                return Response(
                    {"error": "Institution parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            education = self.get_queryset().filter(institution__icontains=institution)
            serializer = self.get_serializer(education, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(
                f"Error getting education by institution: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get education by institution"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Education"],
        responses={200: EducationSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def by_degree(self, request):
        """Get education entries by degree type."""
        try:
            degree = request.query_params.get("degree")
            if not degree:
                return Response(
                    {"error": "Degree parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            education = self.get_queryset().filter(degree__icontains=degree)
            serializer = self.get_serializer(education, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting education by degree: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get education by degree"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Education"],
        responses={200: EducationSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def by_field(self, request):
        """Get education entries by field of study."""
        try:
            field = request.query_params.get("field")
            if not field:
                return Response(
                    {"error": "Field parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            education = self.get_queryset().filter(field_of_study__icontains=field)
            serializer = self.get_serializer(education, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting education by field: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get education by field"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
