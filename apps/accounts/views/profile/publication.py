import logging

from django.contrib.auth import get_user_model
from django.db.models import Count
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from ...models import ActivityLog, Publication
from ...permissions import IsOwnerOrAdmin, can_view_user_profile
from ...serializers import PublicationSerializer
from apps.accounts.views.user import UserRateThrottle
from apps.events.views import StandardResultsSetPagination

logger = logging.getLogger(__name__)
User = get_user_model()


class PublicationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user publications.
    """

    serializer_class = PublicationSerializer
    pagination_class = StandardResultsSetPagination
    throttle_classes = [UserRateThrottle]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["category", "journal", "publisher"]
    search_fields = ["title", "journal", "publisher", "description", "authors"]
    ordering_fields = ["publication_date", "title", "journal"]
    ordering = ["-publication_date"]

    def get_queryset(self):
        """Filter publications based on user and permissions."""
        if self.action == "list":
            # Get user from query params or current user
            user_id = self.request.query_params.get("user_id")
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                    if not can_view_user_profile(self.request.user, user):
                        raise PermissionDenied("Cannot view this user's publications")
                    return Publication.objects.filter(user=user)
                except User.DoesNotExist:
                    return Publication.objects.none()
            else:
                return Publication.objects.filter(user=self.request.user)

        return Publication.objects.filter(user=self.request.user)

    def get_permissions(self):
        if self.action in [
            "list",
            "retrieve",
            "by_category",
            "by_journal",
            "recent",
            "categories",
        ]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        """Create publication for the current user."""
        publication = serializer.save(user=self.request.user)

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Added publication: {publication.title}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_update(self, serializer):
        """Update publication and log activity."""
        publication = serializer.save()

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Updated publication: {publication.title}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_destroy(self, instance):
        """Delete publication and log activity."""
        # Log activity before deletion
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Deleted publication: {instance.title}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

        instance.delete()

    @extend_schema(
        tags=["Publications"],
        responses={200: PublicationSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        """List user publications with filtering and search."""
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error listing publications: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get publications"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Publications"],
        request=PublicationSerializer,
        responses={201: PublicationSerializer},
    )
    def create(self, request, *args, **kwargs):
        """Create a new publication entry."""
        try:
            # Check for duplicate publication
            title = request.data.get("title")
            journal = request.data.get("journal")
            if (
                title
                and journal
                and Publication.objects.filter(
                    user=request.user,
                    title__iexact=title,
                    journal__iexact=journal,
                ).exists()
            ):
                return Response(
                    {"error": "Publication already exists"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return super().create(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error creating publication: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to create publication"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Publications"],
        request=PublicationSerializer,
        responses={200: PublicationSerializer},
    )
    def update(self, request, *args, **kwargs):
        """Update a publication entry."""
        try:
            return super().update(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error updating publication: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to update publication"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Publications"],
        responses={204: None},
    )
    def destroy(self, request, *args, **kwargs):
        """Delete a publication entry."""
        try:
            return super().destroy(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error deleting publication: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to delete publication"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Publications"],
        responses={200: PublicationSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def by_category(self, request):
        """Get publications by category."""
        try:
            category = request.query_params.get("category")
            if not category:
                return Response(
                    {"error": "Category parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            publications = self.get_queryset().filter(category=category)
            serializer = self.get_serializer(publications, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(
                f"Error getting publications by category: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get publications by category"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Publications"],
        responses={200: PublicationSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def by_journal(self, request):
        """Get publications by journal."""
        try:
            journal = request.query_params.get("journal")
            if not journal:
                return Response(
                    {"error": "Journal parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            publications = self.get_queryset().filter(journal__icontains=journal)
            serializer = self.get_serializer(publications, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(
                f"Error getting publications by journal: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get publications by journal"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Publications"],
        responses={200: PublicationSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def recent(self, request):
        """Get recent publications (last 5 years)."""
        try:
            from datetime import timedelta

            from django.utils import timezone

            five_years_ago = timezone.now().date() - timedelta(days=1825)
            recent_publications = self.get_queryset().filter(
                publication_date__gte=five_years_ago
            )
            serializer = self.get_serializer(recent_publications, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting recent publications: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get recent publications"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Publications"],
        responses={200: {"categories": "list"}},
    )
    @action(detail=False, methods=["get"])
    def categories(self, request):
        """Get all publication categories."""
        try:
            categories = [
                {"value": choice[0], "label": choice[1]}
                for choice in Publication.PublicationCategory.choices
            ]
            return Response({"categories": categories})
        except Exception as e:
            logger.error(
                f"Error getting publication categories: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get publication categories"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Publications"],
        responses={200: {"stats": "dict"}},
    )
    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Get publication statistics."""
        try:
            queryset = self.get_queryset()
            total_publications = queryset.count()

            category_stats = {}
            for choice in Publication.PublicationCategory.choices:
                count = queryset.filter(category=choice[0]).count()
                category_stats[choice[1]] = count

            # Get recent publications (last year)
            from datetime import timedelta

            from django.utils import timezone

            one_year_ago = timezone.now().date() - timedelta(days=365)
            recent_count = queryset.filter(publication_date__gte=one_year_ago).count()

            # Get top journals
            top_journals = (
                queryset.values("journal")
                .annotate(count=Count("journal"))
                .order_by("-count")[:5]
            )

            stats = {
                "total_publications": total_publications,
                "recent_publications": recent_count,
                "category_breakdown": category_stats,
                "top_journals": list(top_journals),
            }

            return Response({"stats": stats})
        except Exception as e:
            logger.error(f"Error getting publication stats: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get publication statistics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
