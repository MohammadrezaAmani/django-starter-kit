import logging

from django.contrib.auth import get_user_model

# from apps.accounts.views.user import UserRateThrottle
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.accounts.views.user import UserRateThrottle
from apps.events.views import StandardResultsSetPagination

from ...models import ActivityLog, Certification
from ...permissions import IsOwnerOrAdmin, can_view_user_profile
from ...serializers import CertificationSerializer

logger = logging.getLogger(__name__)
User = get_user_model()


class CertificationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user certifications.
    """

    serializer_class = CertificationSerializer
    pagination_class = StandardResultsSetPagination
    throttle_classes = [UserRateThrottle]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["issuing_organization", "has_expiry", "is_verified"]
    search_fields = ["name", "issuing_organization", "description"]
    ordering_fields = ["issued_date", "expiry_date", "name", "issuing_organization"]
    ordering = ["-issued_date"]

    def get_queryset(self):
        """Filter certifications based on user and permissions."""
        if self.action == "list":
            # Get user from query params or current user
            user_id = self.request.query_params.get("user_id")
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                    if not can_view_user_profile(self.request.user, user):
                        raise PermissionDenied("Cannot view this user's certifications")
                    return Certification.objects.filter(user=user)
                except User.DoesNotExist:
                    return Certification.objects.none()
            else:
                return Certification.objects.filter(user=self.request.user)

        return Certification.objects.filter(user=self.request.user)

    def get_permissions(self):
        if self.action in [
            "list",
            "retrieve",
            "active",
            "by_organization",
            "expiring_soon",
        ]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        """Create certification for the current user."""
        certification = serializer.save(user=self.request.user)

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Added certification: {certification.name} from {certification.issuing_organization}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_update(self, serializer):
        """Update certification and log activity."""
        certification = serializer.save()

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Updated certification: {certification.name} from {certification.issuing_organization}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_destroy(self, instance):
        """Delete certification and log activity."""
        # Log activity before deletion
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Deleted certification: {instance.name} from {instance.issuing_organization}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

        instance.delete()

    @extend_schema(
        tags=["Certifications"],
        responses={200: CertificationSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        """List user certifications with filtering and search."""
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error listing certifications: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get certifications"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Certifications"],
        request=CertificationSerializer,
        responses={201: CertificationSerializer},
    )
    def create(self, request, *args, **kwargs):
        """Create a new certification entry."""
        try:
            # Validate expiry date if has_expiry is True
            if request.data.get("has_expiry") and not request.data.get("expiry_date"):
                return Response(
                    {"error": "Expiry date is required when certification has expiry"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check for duplicate certification
            name = request.data.get("name")
            organization = request.data.get("issuing_organization")
            if (
                name
                and organization
                and Certification.objects.filter(
                    user=request.user,
                    name__iexact=name,
                    issuing_organization__iexact=organization,
                ).exists()
            ):
                return Response(
                    {"error": "Certification already exists"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return super().create(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error creating certification: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to create certification"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Certifications"],
        request=CertificationSerializer,
        responses={200: CertificationSerializer},
    )
    def update(self, request, *args, **kwargs):
        """Update a certification entry."""
        try:
            # Validate expiry date if has_expiry is True
            if request.data.get("has_expiry") and not request.data.get("expiry_date"):
                return Response(
                    {"error": "Expiry date is required when certification has expiry"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return super().update(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error updating certification: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to update certification"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Certifications"],
        responses={204: None},
    )
    def destroy(self, request, *args, **kwargs):
        """Delete a certification entry."""
        try:
            return super().destroy(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error deleting certification: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to delete certification"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Certifications"],
        responses={200: CertificationSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def active(self, request):
        """Get active certifications (non-expired)."""
        try:
            from django.utils import timezone

            active_certs = self.get_queryset().filter(
                Q(has_expiry=False) | Q(expiry_date__gte=timezone.now().date())
            )
            serializer = self.get_serializer(active_certs, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(
                f"Error getting active certifications: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get active certifications"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Certifications"],
        responses={200: CertificationSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def by_organization(self, request):
        """Get certifications by issuing organization."""
        try:
            organization = request.query_params.get("organization")
            if not organization:
                return Response(
                    {"error": "Organization parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            certifications = self.get_queryset().filter(
                issuing_organization__icontains=organization
            )
            serializer = self.get_serializer(certifications, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(
                f"Error getting certifications by organization: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get certifications by organization"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Certifications"],
        responses={200: CertificationSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def expiring_soon(self, request):
        """Get certifications expiring within the next 90 days."""
        try:
            from datetime import timedelta

            from django.utils import timezone

            expiry_threshold = timezone.now().date() + timedelta(days=90)
            expiring_certs = self.get_queryset().filter(
                has_expiry=True,
                expiry_date__lte=expiry_threshold,
                expiry_date__gte=timezone.now().date(),
            )
            serializer = self.get_serializer(expiring_certs, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(
                f"Error getting expiring certifications: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get expiring certifications"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Certifications"],
        responses={200: CertificationSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def verified(self, request):
        """Get verified certifications."""
        try:
            verified_certs = self.get_queryset().filter(is_verified=True)
            serializer = self.get_serializer(verified_certs, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(
                f"Error getting verified certifications: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get verified certifications"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Certifications"],
        responses={200: {"organizations": "list"}},
    )
    @action(detail=False, methods=["get"])
    def organizations(self, request):
        """Get all certification organizations for the user."""
        try:
            organizations = (
                self.get_queryset()
                .values_list("issuing_organization", flat=True)
                .distinct()
                .order_by("issuing_organization")
            )
            return Response({"organizations": list(organizations)})
        except Exception as e:
            logger.error(
                f"Error getting certification organizations: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get certification organizations"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
