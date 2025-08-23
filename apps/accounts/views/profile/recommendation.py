import logging

from django.contrib.auth import get_user_model
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.accounts.views.user import UserRateThrottle
from apps.events.views import StandardResultsSetPagination

from ...models import ActivityLog, Notification, ProfileStats, Recommendation
from ...permissions import (
    CanAccessRecommendation,
    IsOwnerOrAdmin,
    can_view_user_profile,
)
from ...serializers import RecommendationSerializer

logger = logging.getLogger(__name__)
User = get_user_model()


class RecommendationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user recommendations.
    """

    serializer_class = RecommendationSerializer
    pagination_class = StandardResultsSetPagination
    throttle_classes = [UserRateThrottle]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["type", "status", "recommender", "recommended_user"]
    search_fields = ["content", "recommender__first_name", "recommender__last_name"]
    ordering_fields = ["created_at", "updated_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Filter recommendations based on user and permissions."""
        if self.action == "list":
            # Get user from query params or current user
            user_id = self.request.query_params.get("user_id")
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                    if not can_view_user_profile(self.request.user, user):
                        raise PermissionDenied(
                            "Cannot view this user's recommendations"
                        )
                    # Show both received and given recommendations
                    return Recommendation.objects.filter(
                        Q(recommended_user=user) | Q(recommender=user)
                    ).select_related("recommender", "recommended_user")
                except User.DoesNotExist:
                    return Recommendation.objects.none()
            else:
                # For current user, show both received and given
                return Recommendation.objects.filter(
                    Q(recommended_user=self.request.user)
                    | Q(recommender=self.request.user)
                ).select_related("recommender", "recommended_user")

        return Recommendation.objects.filter(
            Q(recommended_user=self.request.user) | Q(recommender=self.request.user)
        ).select_related("recommender", "recommended_user")

    def get_permissions(self):
        if self.action in [
            "list",
            "retrieve",
            "received",
            "given",
            "by_type",
            "pending",
        ]:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ["create", "request_recommendation"]:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ["approve", "decline"]:
            permission_classes = [permissions.IsAuthenticated, CanAccessRecommendation]
        else:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        """Create recommendation for the specified user."""
        recommendation = serializer.save(recommender=self.request.user)

        # Create notification for the recommended user
        Notification.objects.create(
            recipient=recommendation.recommended_user,
            sender=self.request.user,
            notification_type=Notification.NotificationType.RECOMMENDATION_RECEIVED,
            title=f"{self.request.user.get_full_name()} wrote you a recommendation",
            message=f"{self.request.user.get_full_name()} wrote you a {recommendation.get_type_display().lower()} recommendation.",
            data={"recommendation_id": str(recommendation.id)},
        )

        # Update profile stats
        stats, created = ProfileStats.objects.get_or_create(
            user=recommendation.recommended_user
        )
        stats.recommendations_count = Recommendation.objects.filter(
            recommended_user=recommendation.recommended_user,
            status=Recommendation.RecommendationStatus.APPROVED,
        ).count()
        stats.save()

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.RECOMMENDATION_GIVEN,
            description=f"Wrote recommendation for {recommendation.recommended_user.get_full_name()}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_update(self, serializer):
        """Update recommendation and log activity."""
        recommendation = serializer.save()

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.RECOMMENDATION_UPDATED,
            description=f"Updated recommendation for {recommendation.recommended_user.get_full_name()}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_destroy(self, instance):
        """Delete recommendation and log activity."""
        # Update profile stats
        stats, created = ProfileStats.objects.get_or_create(
            user=instance.recommended_user
        )

        # Log activity before deletion
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.RECOMMENDATION_DELETED,
            description=f"Deleted recommendation for {instance.recommended_user.get_full_name()}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

        instance.delete()

        # Recalculate stats after deletion
        stats.recommendations_count = Recommendation.objects.filter(
            recommended_user=instance.recommended_user,
            status=Recommendation.RecommendationStatus.APPROVED,
        ).count()
        stats.save()

    @extend_schema(
        tags=["Recommendations"],
        responses={200: RecommendationSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        """List recommendations with filtering and search."""
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error listing recommendations: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get recommendations"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Recommendations"],
        request=RecommendationSerializer,
        responses={201: RecommendationSerializer},
    )
    def create(self, request, *args, **kwargs):
        """Create a new recommendation."""
        try:
            recommended_user_id = request.data.get("recommended_user")
            if not recommended_user_id:
                return Response(
                    {"error": "Recommended user is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check if user is trying to recommend themselves
            if str(recommended_user_id) == str(request.user.id):
                return Response(
                    {"error": "Cannot recommend yourself"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check if recommendation already exists
            existing = Recommendation.objects.filter(
                recommender=request.user,
                recommended_user_id=recommended_user_id,
            ).first()

            if existing:
                return Response(
                    {"error": "Recommendation already exists"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return super().create(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error creating recommendation: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to create recommendation"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Recommendations"],
        responses={200: RecommendationSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def received(self, request):
        """Get recommendations received by the user."""
        try:
            user_id = request.query_params.get("user_id", request.user.id)
            try:
                user = User.objects.get(id=user_id)
                if not can_view_user_profile(request.user, user):
                    raise PermissionDenied("Cannot view this user's recommendations")
            except User.DoesNotExist:
                return Response(
                    {"error": "User not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            recommendations = Recommendation.objects.filter(
                recommended_user=user,
                status=Recommendation.RecommendationStatus.APPROVED,
            ).select_related("recommender")

            page = self.paginate_queryset(recommendations)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(recommendations, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(
                f"Error getting received recommendations: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get received recommendations"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Recommendations"],
        responses={200: RecommendationSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def given(self, request):
        """Get recommendations given by the user."""
        try:
            recommendations = Recommendation.objects.filter(
                recommender=request.user
            ).select_related("recommended_user")

            page = self.paginate_queryset(recommendations)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(recommendations, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(
                f"Error getting given recommendations: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get given recommendations"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Recommendations"],
        responses={200: RecommendationSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def pending(self, request):
        """Get pending recommendations for the user to approve."""
        try:
            pending_recommendations = Recommendation.objects.filter(
                recommended_user=request.user,
                status=Recommendation.RecommendationStatus.PENDING,
            ).select_related("recommender")

            serializer = self.get_serializer(pending_recommendations, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(
                f"Error getting pending recommendations: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get pending recommendations"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Recommendations"],
        responses={200: RecommendationSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def by_type(self, request):
        """Get recommendations by type."""
        try:
            recommendation_type = request.query_params.get("type")
            if not recommendation_type:
                return Response(
                    {"error": "Type parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user_id = request.query_params.get("user_id", request.user.id)
            try:
                user = User.objects.get(id=user_id)
                if not can_view_user_profile(request.user, user):
                    raise PermissionDenied("Cannot view this user's recommendations")
            except User.DoesNotExist:
                return Response(
                    {"error": "User not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            recommendations = Recommendation.objects.filter(
                recommended_user=user,
                type=recommendation_type,
                status=Recommendation.RecommendationStatus.APPROVED,
            ).select_related("recommender")

            serializer = self.get_serializer(recommendations, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(
                f"Error getting recommendations by type: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get recommendations by type"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Recommendations"],
        responses={200: RecommendationSerializer},
    )
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Approve a pending recommendation."""
        try:
            recommendation = self.get_object()

            if recommendation.recommended_user != request.user:
                return Response(
                    {"error": "Can only approve your own recommendations"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            if recommendation.status != Recommendation.RecommendationStatus.PENDING:
                return Response(
                    {"error": "Recommendation is not pending"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            recommendation.status = Recommendation.RecommendationStatus.APPROVED
            recommendation.save()

            # Update profile stats
            stats, created = ProfileStats.objects.get_or_create(user=request.user)
            stats.recommendations_count = Recommendation.objects.filter(
                recommended_user=request.user,
                status=Recommendation.RecommendationStatus.APPROVED,
            ).count()
            stats.save()

            # Create notification for recommender
            Notification.objects.create(
                recipient=recommendation.recommender,
                sender=request.user,
                notification_type=Notification.NotificationType.RECOMMENDATION_APPROVED,
                title=f"{request.user.get_full_name()} approved your recommendation",
                message=f"{request.user.get_full_name()} approved your recommendation.",
                data={"recommendation_id": str(recommendation.id)},
            )

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                activity_type=ActivityLog.ActivityType.RECOMMENDATION_APPROVED,
                description=f"Approved recommendation from {recommendation.recommender.get_full_name()}",
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            serializer = self.get_serializer(recommendation)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error approving recommendation: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to approve recommendation"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Recommendations"],
        responses={200: RecommendationSerializer},
    )
    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        """Decline a pending recommendation."""
        try:
            recommendation = self.get_object()

            if recommendation.recommended_user != request.user:
                return Response(
                    {"error": "Can only decline your own recommendations"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            if recommendation.status != Recommendation.RecommendationStatus.PENDING:
                return Response(
                    {"error": "Recommendation is not pending"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            recommendation.status = Recommendation.RecommendationStatus.DECLINED
            recommendation.save()

            # Create notification for recommender
            Notification.objects.create(
                recipient=recommendation.recommender,
                sender=request.user,
                notification_type=Notification.NotificationType.RECOMMENDATION_DECLINED,
                title=f"{request.user.get_full_name()} declined your recommendation",
                message=f"{request.user.get_full_name()} declined your recommendation.",
                data={"recommendation_id": str(recommendation.id)},
            )

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                activity_type=ActivityLog.ActivityType.RECOMMENDATION_DECLINED,
                description=f"Declined recommendation from {recommendation.recommender.get_full_name()}",
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            serializer = self.get_serializer(recommendation)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error declining recommendation: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to decline recommendation"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Recommendations"],
        responses={201: RecommendationSerializer},
    )
    @action(detail=False, methods=["post"])
    def request_recommendation(self, request):
        """Request a recommendation from another user."""
        try:
            recommender_id = request.data.get("recommender_id")
            recommendation_type = request.data.get("type")
            message = request.data.get("message", "")

            if not recommender_id:
                return Response(
                    {"error": "Recommender ID is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not recommendation_type:
                return Response(
                    {"error": "Recommendation type is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                recommender = User.objects.get(id=recommender_id)
            except User.DoesNotExist:
                return Response(
                    {"error": "Recommender not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Check if user is trying to request from themselves
            if recommender == request.user:
                return Response(
                    {"error": "Cannot request recommendation from yourself"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check if request already exists
            existing = Recommendation.objects.filter(
                recommender=recommender,
                recommended_user=request.user,
                status=Recommendation.RecommendationStatus.REQUESTED,
            ).first()

            if existing:
                return Response(
                    {"error": "Recommendation request already exists"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Create recommendation request
            recommendation = Recommendation.objects.create(
                recommender=recommender,
                recommended_user=request.user,
                type=recommendation_type,
                status=Recommendation.RecommendationStatus.REQUESTED,
                content=message,
            )

            # Create notification for recommender
            Notification.objects.create(
                recipient=recommender,
                sender=request.user,
                notification_type=Notification.NotificationType.RECOMMENDATION_REQUEST,
                title=f"{request.user.get_full_name()} requested a recommendation",
                message=f"{request.user.get_full_name()} requested a {recommendation.get_type_display().lower()} recommendation from you.",
                data={"recommendation_id": str(recommendation.id)},
            )

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                activity_type=ActivityLog.ActivityType.RECOMMENDATION_REQUESTED,
                description=f"Requested recommendation from {recommender.get_full_name()}",
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            serializer = self.get_serializer(recommendation)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"Error requesting recommendation: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to request recommendation"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Recommendations"],
        responses={200: {"types": "list"}},
    )
    @action(detail=False, methods=["get"])
    def types(self, request):
        """Get available recommendation types."""
        try:
            types = [
                {"value": choice[0], "label": choice[1]}
                for choice in Recommendation.RecommendationType.choices
            ]
            return Response({"types": types})
        except Exception as e:
            logger.error(f"Error getting recommendation types: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get recommendation types"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Recommendations"],
        responses={200: {"stats": "dict"}},
    )
    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Get recommendation statistics."""
        try:
            # Get recommendations received
            received_count = Recommendation.objects.filter(
                recommended_user=request.user,
                status=Recommendation.RecommendationStatus.APPROVED,
            ).count()

            # Get recommendations given
            given_count = Recommendation.objects.filter(
                recommender=request.user,
                status=Recommendation.RecommendationStatus.APPROVED,
            ).count()

            # Get pending recommendations to approve
            pending_count = Recommendation.objects.filter(
                recommended_user=request.user,
                status=Recommendation.RecommendationStatus.PENDING,
            ).count()

            # Get requested recommendations
            requested_count = Recommendation.objects.filter(
                recommended_user=request.user,
                status=Recommendation.RecommendationStatus.REQUESTED,
            ).count()

            # Get breakdown by type
            type_breakdown = {}
            for choice in Recommendation.RecommendationType.choices:
                count = Recommendation.objects.filter(
                    recommended_user=request.user,
                    type=choice[0],
                    status=Recommendation.RecommendationStatus.APPROVED,
                ).count()
                type_breakdown[choice[1]] = count

            stats = {
                "received_count": received_count,
                "given_count": given_count,
                "pending_count": pending_count,
                "requested_count": requested_count,
                "type_breakdown": type_breakdown,
            }

            return Response({"stats": stats})
        except Exception as e:
            logger.error(f"Error getting recommendation stats: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get recommendation statistics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
