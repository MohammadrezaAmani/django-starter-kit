import logging

from django.contrib.auth import get_user_model
from django.db.models import Count
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from ...models import ActivityLog, Notification, ProfileStats, Skill, SkillEndorsement
from ...permissions import IsOwnerOrAdmin, can_endorse_skill, can_view_user_profile
from ...serializers import SkillEndorsementSerializer, SkillSerializer
from ..user import StandardResultsSetPagination, UserThrottle

logger = logging.getLogger(__name__)
User = get_user_model()


class SkillViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user skills and endorsements.
    """

    serializer_class = SkillSerializer
    pagination_class = StandardResultsSetPagination
    throttle_classes = [UserThrottle]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["category", "level", "years_of_experience"]
    search_fields = ["name", "category"]
    ordering_fields = ["name", "level", "years_of_experience", "last_used"]
    ordering = ["-level", "name"]

    def get_queryset(self):
        """Filter skills based on user and permissions."""
        if self.action == "list":
            # Get user from query params or current user
            user_id = self.request.query_params.get("user_id")
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                    if not can_view_user_profile(self.request.user, user):
                        raise PermissionDenied("Cannot view this user's skills")
                    return Skill.objects.filter(user=user).prefetch_related(
                        "endorsements__endorser"
                    )
                except User.DoesNotExist:
                    return Skill.objects.none()
            else:
                return Skill.objects.filter(user=self.request.user).prefetch_related(
                    "endorsements__endorser"
                )

        return Skill.objects.filter(user=self.request.user).prefetch_related(
            "endorsements__endorser"
        )

    def get_permissions(self):
        if self.action in ["list", "retrieve", "top_skills", "by_category"]:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ["endorse", "remove_endorsement"]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        """Create skill for the current user."""
        skill = serializer.save(user=self.request.user)

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.SKILL_UPDATE,
            description=f"Added skill: {skill.name}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_update(self, serializer):
        """Update skill and log activity."""
        skill = serializer.save()

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.SKILL_UPDATE,
            description=f"Updated skill: {skill.name}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_destroy(self, instance):
        """Delete skill and log activity."""
        # Log activity before deletion
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.SKILL_UPDATE,
            description=f"Deleted skill: {instance.name}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

        instance.delete()

    @extend_schema(
        tags=["Skills"],
        responses={200: SkillSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        """List user skills with filtering and search."""
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error listing skills: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get skills"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Skills"],
        request=SkillSerializer,
        responses={201: SkillSerializer},
    )
    def create(self, request, *args, **kwargs):
        """Create a new skill entry."""
        try:
            # Check if skill already exists for this user
            skill_name = request.data.get("name")
            if (
                skill_name
                and Skill.objects.filter(
                    user=request.user, name__iexact=skill_name
                ).exists()
            ):
                return Response(
                    {"error": "Skill already exists"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return super().create(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error creating skill: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to create skill"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Skills"],
        request=SkillSerializer,
        responses={200: SkillSerializer},
    )
    def update(self, request, *args, **kwargs):
        """Update a skill entry."""
        try:
            return super().update(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error updating skill: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to update skill"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Skills"],
        responses={204: None},
    )
    def destroy(self, request, *args, **kwargs):
        """Delete a skill entry."""
        try:
            return super().destroy(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error deleting skill: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to delete skill"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Skills"],
        request=SkillEndorsementSerializer,
        responses={201: SkillEndorsementSerializer},
    )
    @action(detail=True, methods=["post"])
    def endorse(self, request, pk=None):
        """Endorse a skill."""
        try:
            skill = self.get_object()
            skill_owner = skill.user

            if not can_endorse_skill(request.user, skill_owner):
                return Response(
                    {"error": "Cannot endorse this user's skills"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Check if already endorsed
            existing_endorsement = SkillEndorsement.objects.filter(
                skill=skill,
                endorser=request.user,
            ).first()

            if existing_endorsement:
                return Response(
                    {"error": "Skill already endorsed"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            endorsement = SkillEndorsement.objects.create(
                skill=skill,
                endorser=request.user,
                message=request.data.get("message", ""),
            )

            # Update endorsement count
            stats, created = ProfileStats.objects.get_or_create(user=skill_owner)
            stats.endorsements_count = SkillEndorsement.objects.filter(
                skill__user=skill_owner
            ).count()
            stats.save()

            # Create notification
            Notification.objects.create(
                recipient=skill_owner,
                sender=request.user,
                notification_type=Notification.NotificationType.SKILL_ENDORSEMENT,
                title=f"{request.user.get_full_name()} endorsed your {skill.name} skill",
                message=f"{request.user.get_full_name()} endorsed your {skill.name} skill.",
                data={"skill_id": str(skill.id), "endorsement_id": str(endorsement.id)},
            )

            logger.info(
                f"Skill endorsed: {skill.name} by {request.user.username} for {skill_owner.username}"
            )
            return Response(
                SkillEndorsementSerializer(endorsement).data,
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.error(f"Error endorsing skill: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to endorse skill"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Skills"],
        responses={204: None},
    )
    @action(detail=True, methods=["delete"], url_path="remove-endorsement")
    def remove_endorsement(self, request, pk=None):
        """Remove endorsement from a skill."""
        try:
            skill = self.get_object()

            endorsement = SkillEndorsement.objects.filter(
                skill=skill,
                endorser=request.user,
            ).first()

            if not endorsement:
                return Response(
                    {"error": "Endorsement not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            endorsement.delete()

            # Update endorsement count
            skill_owner = skill.user
            stats, created = ProfileStats.objects.get_or_create(user=skill_owner)
            stats.endorsements_count = SkillEndorsement.objects.filter(
                skill__user=skill_owner
            ).count()
            stats.save()

            logger.info(f"Endorsement removed: {skill.name} by {request.user.username}")
            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception as e:
            logger.error(f"Error removing endorsement: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to remove endorsement"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Skills"],
        responses={200: SkillSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def top_skills(self, request):
        """Get user's top skills by endorsement count and level."""
        try:
            top_skills = (
                self.get_queryset()
                .annotate(endorsement_count=Count("endorsements"))
                .order_by("-endorsement_count", "-level")[:10]
            )
            serializer = self.get_serializer(top_skills, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting top skills: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get top skills"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Skills"],
        responses={200: SkillSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def by_category(self, request):
        """Get skills grouped by category."""
        try:
            category = request.query_params.get("category")
            if not category:
                return Response(
                    {"error": "Category parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            skills = self.get_queryset().filter(category__iexact=category)
            serializer = self.get_serializer(skills, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting skills by category: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get skills by category"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Skills"],
        responses={200: {"categories": "list"}},
    )
    @action(detail=False, methods=["get"])
    def categories(self, request):
        """Get all skill categories for the user."""
        try:
            categories = (
                self.get_queryset()
                .values_list("category", flat=True)
                .distinct()
                .order_by("category")
            )
            return Response({"categories": list(categories)})
        except Exception as e:
            logger.error(f"Error getting skill categories: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get skill categories"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Skills"],
        responses={200: SkillEndorsementSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def endorsements(self, request, pk=None):
        """Get endorsements for a specific skill."""
        try:
            skill = self.get_object()
            endorsements = skill.endorsements.select_related("endorser").order_by(
                "-created_at"
            )

            page = self.paginate_queryset(endorsements)
            if page is not None:
                serializer = SkillEndorsementSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = SkillEndorsementSerializer(endorsements, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting skill endorsements: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get skill endorsements"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
