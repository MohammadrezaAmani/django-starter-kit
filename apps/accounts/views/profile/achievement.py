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

from ...models import Achievement, ActivityLog
from ...permissions import IsOwnerOrAdmin, can_view_user_profile
from ...serializers import AchievementSerializer

logger = logging.getLogger(__name__)
User = get_user_model()


class AchievementViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user achievements and awards.
    """

    serializer_class = AchievementSerializer
    pagination_class = StandardResultsSetPagination
    throttle_classes = [UserRateThrottle]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["category", "issuer"]
    search_fields = ["title", "issuer", "description"]
    ordering_fields = ["date_received", "title", "issuer"]
    ordering = ["-date_received"]

    def get_queryset(self):
        """Filter achievements based on user and permissions."""
        if self.action == "list":
            # Get user from query params or current user
            user_id = self.request.query_params.get("user_id")
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                    if not can_view_user_profile(self.request.user, user):
                        raise PermissionDenied("Cannot view this user's achievements")
                    return Achievement.objects.filter(user=user)
                except User.DoesNotExist:
                    return Achievement.objects.none()
            else:
                return Achievement.objects.filter(user=self.request.user)

        return Achievement.objects.filter(user=self.request.user)

    def get_permissions(self):
        if self.action in [
            "list",
            "retrieve",
            "by_category",
            "by_issuer",
            "recent",
        ]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        """Create achievement for the current user."""
        achievement = serializer.save(user=self.request.user)

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Added achievement: {achievement.title} from {achievement.issuer}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_update(self, serializer):
        """Update achievement and log activity."""
        achievement = serializer.save()

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Updated achievement: {achievement.title} from {achievement.issuer}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_destroy(self, instance):
        """Delete achievement and log activity."""
        # Log activity before deletion
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Deleted achievement: {instance.title} from {instance.issuer}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

        instance.delete()

    @extend_schema(
        tags=["Achievements"],
        responses={200: AchievementSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        """List user achievements with filtering and search."""
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error listing achievements: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get achievements"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Achievements"],
        request=AchievementSerializer,
        responses={201: AchievementSerializer},
    )
    def create(self, request, *args, **kwargs):
        """Create a new achievement entry."""
        try:
            # Check for duplicate achievement
            title = request.data.get("title")
            issuer = request.data.get("issuer")
            if (
                title
                and issuer
                and Achievement.objects.filter(
                    user=request.user,
                    title__iexact=title,
                    issuer__iexact=issuer,
                ).exists()
            ):
                return Response(
                    {"error": "Achievement already exists"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return super().create(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error creating achievement: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to create achievement"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Achievements"],
        request=AchievementSerializer,
        responses={200: AchievementSerializer},
    )
    def update(self, request, *args, **kwargs):
        """Update an achievement entry."""
        try:
            return super().update(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error updating achievement: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to update achievement"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Achievements"],
        responses={204: None},
    )
    def destroy(self, request, *args, **kwargs):
        """Delete an achievement entry."""
        try:
            return super().destroy(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error deleting achievement: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to delete achievement"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Achievements"],
        responses={200: AchievementSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def by_category(self, request):
        """Get achievements by category."""
        try:
            category = request.query_params.get("category")
            if not category:
                return Response(
                    {"error": "Category parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            achievements = self.get_queryset().filter(category=category)
            serializer = self.get_serializer(achievements, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(
                f"Error getting achievements by category: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get achievements by category"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Achievements"],
        responses={200: AchievementSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def by_issuer(self, request):
        """Get achievements by issuer."""
        try:
            issuer = request.query_params.get("issuer")
            if not issuer:
                return Response(
                    {"error": "Issuer parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            achievements = self.get_queryset().filter(issuer__icontains=issuer)
            serializer = self.get_serializer(achievements, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(
                f"Error getting achievements by issuer: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get achievements by issuer"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Achievements"],
        responses={200: AchievementSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def recent(self, request):
        """Get recent achievements (last 2 years)."""
        try:
            from datetime import timedelta

            from django.utils import timezone

            two_years_ago = timezone.now().date() - timedelta(days=730)
            recent_achievements = self.get_queryset().filter(
                date_received__gte=two_years_ago
            )
            serializer = self.get_serializer(recent_achievements, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting recent achievements: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get recent achievements"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Achievements"],
        responses={200: {"categories": "list"}},
    )
    @action(detail=False, methods=["get"])
    def categories(self, request):
        """Get all achievement categories for the user."""
        try:
            categories = [
                {"value": choice[0], "label": choice[1]}
                for choice in Achievement.AchievementCategory.choices
            ]
            return Response({"categories": categories})
        except Exception as e:
            logger.error(
                f"Error getting achievement categories: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get achievement categories"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Achievements"],
        responses={200: {"stats": "dict"}},
    )
    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Get achievement statistics."""
        try:
            queryset = self.get_queryset()
            total_achievements = queryset.count()

            category_stats = {}
            for choice in Achievement.AchievementCategory.choices:
                count = queryset.filter(category=choice[0]).count()
                category_stats[choice[1]] = count

            # Get recent achievements (last year)
            from datetime import timedelta

            from django.utils import timezone

            one_year_ago = timezone.now().date() - timedelta(days=365)
            recent_count = queryset.filter(date_received__gte=one_year_ago).count()

            stats = {
                "total_achievements": total_achievements,
                "recent_achievements": recent_count,
                "category_breakdown": category_stats,
            }

            return Response({"stats": stats})
        except Exception as e:
            logger.error(f"Error getting achievement stats: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get achievement statistics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
