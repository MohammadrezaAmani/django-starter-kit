import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import models
from django.db.models import Case, Count, F, Q, When
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.accounts.filters import UserFilter
from apps.accounts.models import (
    ActivityLog,
    Connection,
    Follow,
    ProfileView,
    Skill,
    SkillEndorsement,
    UserProfile,
)
from apps.accounts.permissions import CanViewProfile, IsOwnerOrReadOnly, IsProfileOwner
from apps.accounts.serializers import (
    BulkOperationSerializer,
    ConnectionRequestSerializer,
    ConnectionSerializer,
    FollowSerializer,
    OnlineStatusSerializer,
    ProfileAnalyticsSerializer,
    ProfileBasicInfoSerializer,
    ProfileListResponseSerializer,
    ProfileSearchSerializer,
    SkillEndorseSerializer,
    StatusUpdateSerializer,
    UserBasicSerializer,
    UserSerializer,
)
from apps.common.mixins import CacheableViewSetMixin, SecurityMixin
from apps.common.pagination import CustomPageNumberPagination
from apps.common.utils import get_client_ip, get_user_agent

logger = logging.getLogger(__name__)

User = get_user_model()


class UserRateThrottle(UserRateThrottle):
    """Custom rate limiting for user operations"""

    scope = "user"


@extend_schema_view(
    list=extend_schema(
        summary="List Users",
        description="Get paginated list of users with filtering and search",
        parameters=[
            OpenApiParameter(
                "search", str, description="Search in name, username, email"
            ),
            OpenApiParameter("skills", str, description="Filter by skills"),
            OpenApiParameter("location", str, description="Filter by location"),
            OpenApiParameter("company", str, description="Filter by current company"),
            OpenApiParameter("is_online", bool, description="Filter by online status"),
            OpenApiParameter(
                "ordering",
                str,
                description="Order by: name, joined_date, last_activity",
            ),
        ],
    ),
    retrieve=extend_schema(
        summary="Get User Profile",
        description="Get detailed user profile information",
    ),
    update=extend_schema(
        summary="Update User Profile",
        description="Update user profile (owner only)",
    ),
    partial_update=extend_schema(
        summary="Partially Update User Profile",
        description="Partially update user profile (owner only)",
    ),
)
class UserViewSet(CacheableViewSetMixin, SecurityMixin, viewsets.ModelViewSet):
    """
    Advanced user profile management with:
    - Comprehensive search and filtering
    - Privacy controls
    - Analytics tracking
    - Connection management
    - Activity monitoring
    """

    queryset = User.objects.select_related("profile").prefetch_related(
        "social_links",
        "skills",
        "experience",
        "educations",
        "projects",
        "languages",
        "achievements",
        "connections_received",
        "connections_sent",
        "followers",
        "following",
    )
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]
    throttle_classes = [UserRateThrottle]
    pagination_class = CustomPageNumberPagination
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = UserFilter
    search_fields = [
        "username",
        "first_name",
        "last_name",
        "email",
        "profile__bio",
        "profile__headline",
        "profile__current_company",
        "profile__location",
        "skills__name",
    ]
    ordering_fields = [
        "username",
        "first_name",
        "last_name",
        "date_joined",
        "last_login",
        "profile__updated_at",
        "profile__profile_views_count",
    ]
    ordering = ["-date_joined"]

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == "list":
            return UserBasicSerializer
        elif self.action in ["search_profiles", "suggestions"]:
            return UserBasicSerializer
        elif self.action in ["analytics", "profile_stats"]:
            return ProfileAnalyticsSerializer
        elif self.action == "update_basic_info":
            return ProfileBasicInfoSerializer
        elif self.action == "update_status":
            return StatusUpdateSerializer
        elif self.action == "online_status":
            return OnlineStatusSerializer
        return UserSerializer

    def get_permissions(self):
        """Set permissions based on action"""
        if self.action in ["destroy", "update", "partial_update"]:
            permission_classes = [IsAuthenticated, IsProfileOwner]
        elif self.action in ["analytics", "activity_log", "connections_data"]:
            permission_classes = [IsAuthenticated, IsProfileOwner]
        elif self.action in ["retrieve"]:
            permission_classes = [CanViewProfile]
        else:
            permission_classes = [IsAuthenticatedOrReadOnly]

        return [permission() for permission in permission_classes]

    def get_queryset(self):
        """Filter queryset based on privacy settings and user permissions"""
        queryset = super().get_queryset()

        # If user is not authenticated, only show public profiles
        if not self.request.user.is_authenticated:
            queryset = queryset.filter(
                profile__profile_visibility=UserProfile.ProfileVisibility.PUBLIC
            )
        else:
            # For authenticated users, apply privacy filters
            user = self.request.user

            # Include public profiles
            public_q = Q(
                profile__profile_visibility=UserProfile.ProfileVisibility.PUBLIC
            )

            # Include own profile
            own_q = Q(id=user.id)

            # Include connection-only profiles if connected
            connected_users = Connection.objects.filter(
                Q(from_user=user) | Q(to_user=user),
                status=Connection.ConnectionStatus.ACCEPTED,
            ).values_list("from_user_id", "to_user_id")

            connected_ids = set()
            for from_user_id, to_user_id in connected_users:
                connected_ids.add(
                    from_user_id if from_user_id != user.id else to_user_id
                )

            connections_q = Q(
                profile__profile_visibility=UserProfile.ProfileVisibility.CONNECTIONS_ONLY,
                id__in=connected_ids,
            )

            queryset = queryset.filter(public_q | own_q | connections_q)

        return queryset.distinct()

    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        """Get user profile with view tracking"""
        instance = self.get_object()

        # Track profile view if not own profile
        if request.user.is_authenticated and request.user != instance:
            self.track_profile_view(request.user, instance)

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def track_profile_view(self, viewer: User, viewed: User) -> None:  # type: ignore
        """Track profile view for analytics"""
        try:
            # Create or update profile view
            profile_view, created = ProfileView.objects.get_or_create(
                viewer=viewer,
                viewed=viewed,
                defaults={"view_count": 1, "last_viewed": timezone.now()},
            )

            if not created:
                profile_view.view_count += 1
                profile_view.last_viewed = timezone.now()
                profile_view.save(update_fields=["view_count", "last_viewed"])

            # Update profile stats
            if hasattr(viewed, "profile"):
                viewed.profile.profile_views_count = F("profile_views_count") + 1
                viewed.profile.save(update_fields=["profile_views_count"])

        except Exception as e:
            logger.error(f"Failed to track profile view: {e}")

    @extend_schema(
        summary="Search Profiles",
        description="Advanced profile search with filters",
        request=ProfileSearchSerializer,
        responses={200: ProfileListResponseSerializer},
    )
    @action(detail=False, methods=["post"])
    def search_profiles(self, request: Request) -> Response:
        """Advanced profile search with multiple filters"""
        serializer = ProfileSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        query_params = serializer.validated_data
        queryset = self.get_queryset()

        # Apply search filters
        if query_params.get("query"):
            search_query = query_params["query"]
            queryset = queryset.filter(
                Q(first_name__icontains=search_query)
                | Q(last_name__icontains=search_query)
                | Q(username__icontains=search_query)
                | Q(profile__headline__icontains=search_query)
                | Q(profile__bio__icontains=search_query)
            )

        if query_params.get("skills"):
            skills = query_params["skills"]
            queryset = queryset.filter(skills__name__in=skills).annotate(
                skill_match_count=Count("skills", distinct=True)
            )

        if query_params.get("location"):
            queryset = queryset.filter(
                profile__location__icontains=query_params["location"]
            )

        if query_params.get("company"):
            queryset = queryset.filter(
                profile__current_company__icontains=query_params["company"]
            )

        if query_params.get("experience"):
            queryset = queryset.filter(
                experience__title__icontains=query_params["experience"]
            )

        if query_params.get("education"):
            queryset = queryset.filter(
                educations__institution__icontains=query_params["education"]
            )

        # Apply sorting
        sort_by = query_params.get("sort_by", "relevance")
        sort_order = query_params.get("sort_order", "desc")
        order_prefix = "-" if sort_order == "desc" else ""

        if sort_by == "relevance":
            # Sort by skill match count if skills provided, otherwise by profile completeness
            if query_params.get("skills"):
                queryset = queryset.order_by(f"{order_prefix}skill_match_count")
            else:
                queryset = queryset.order_by(f"{order_prefix}profile__updated_at")
        elif sort_by == "name":
            queryset = queryset.order_by(
                f"{order_prefix}first_name", f"{order_prefix}last_name"
            )
        elif sort_by == "experience":
            queryset = queryset.order_by(f"{order_prefix}profile__years_of_experience")
        elif sort_by == "connections":
            queryset = queryset.annotate(
                connections_count=Count(
                    "connections_received",
                    filter=Q(
                        connections_received__status=Connection.ConnectionStatus.ACCEPTED
                    ),
                )
            ).order_by(f"{order_prefix}connections_count")

        # Paginate results
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = UserBasicSerializer(
                page, many=True, context={"request": request}
            )
            return self.get_paginated_response(serializer.data)

        serializer = UserBasicSerializer(
            queryset, many=True, context={"request": request}
        )
        return Response(serializer.data)

    @extend_schema(
        summary="Get Profile Suggestions",
        description="Get suggested profiles based on user interests and connections",
        responses={200: UserBasicSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def suggestions(self, request: Request) -> Response:
        """Get personalized profile suggestions"""
        user = request.user
        cache_key = f"profile_suggestions:{user.id}"

        # Try to get from cache first
        cached_suggestions = cache.get(cache_key)
        if cached_suggestions:
            return Response(cached_suggestions)

        # Get user's skills and connections for better suggestions
        user_skills = (
            list(user.profile.skills.values_list("name", flat=True))
            if hasattr(user, "profile")
            else []
        )
        connected_user_ids = list(
            Connection.objects.filter(
                Q(from_user=user) | Q(to_user=user),
                status=Connection.ConnectionStatus.ACCEPTED,
            ).values_list("from_user_id", "to_user_id")
        )

        # Flatten connection IDs and exclude current user
        connected_ids = set()
        for from_id, to_id in connected_user_ids:
            connected_ids.add(from_id if from_id != user.id else to_id)
        connected_ids.add(user.id)  # Exclude self

        queryset = self.get_queryset().exclude(id__in=connected_ids)

        # Prioritize users with similar skills
        if user_skills:
            queryset = (
                queryset.filter(skills__name__in=user_skills)
                .annotate(common_skills_count=Count("skills", distinct=True))
                .order_by("-common_skills_count")
            )

        # Add other ranking factors
        queryset = queryset.annotate(
            profile_completeness_score=Case(
                When(profile__bio__isnull=False, then=1),
                default=0,
                output_field=models.IntegerField(),
            )
            + Case(
                When(profile__avatar__isnull=False, then=1),
                default=0,
                output_field=models.IntegerField(),
            )
            + Case(
                When(experience__isnull=False, then=1),
                default=0,
                output_field=models.IntegerField(),
            )
        ).order_by("-profile_completeness_score")

        # Limit to top 10 suggestions
        suggestions = queryset[:10]
        serializer = UserBasicSerializer(
            suggestions, many=True, context={"request": request}
        )

        # Cache for 1 hour
        cache.set(cache_key, serializer.data, 3600)

        return Response(serializer.data)

    @extend_schema(
        summary="Send Connection Request",
        description="Send connection request to another user",
        request=ConnectionRequestSerializer,
        responses={201: ConnectionSerializer},
    )
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def connect(self, request: Request, pk=None) -> Response:
        """Send connection request to user"""
        target_user = self.get_object()
        current_user = request.user

        if target_user == current_user:
            return Response(
                {"error": "Cannot connect to yourself"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if connection already exists
        existing_connection = Connection.objects.filter(
            Q(from_user=current_user, to_user=target_user)
            | Q(from_user=target_user, to_user=current_user)
        ).first()

        if existing_connection:
            if existing_connection.status == Connection.ConnectionStatus.ACCEPTED:
                return Response(
                    {"error": "Already connected"}, status=status.HTTP_400_BAD_REQUEST
                )
            elif existing_connection.status == Connection.ConnectionStatus.PENDING:
                return Response(
                    {"error": "Connection request already sent"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Create connection request
        connection = Connection.objects.create(
            from_user=current_user,
            to_user=target_user,
            status=Connection.ConnectionStatus.PENDING,
        )

        # Log activity
        ActivityLog.objects.create(
            user=current_user,
            activity_type=ActivityLog.ActivityType.CONNECTION_REQUEST,
            description=f"Sent connection request to {target_user.get_full_name()}",
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )

        serializer = ConnectionSerializer(connection, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Follow User",
        description="Follow or unfollow a user",
        responses={200: FollowSerializer},
    )
    @action(
        detail=True, methods=["post", "delete"], permission_classes=[IsAuthenticated]
    )
    def follow(self, request: Request, pk=None) -> Response:
        """Follow or unfollow user"""
        target_user = self.get_object()
        current_user = request.user

        if target_user == current_user:
            return Response(
                {"error": "Cannot follow yourself"}, status=status.HTTP_400_BAD_REQUEST
            )

        if request.method == "POST":
            follow_obj, created = Follow.objects.get_or_create(
                follower=current_user, following=target_user
            )

            if created:
                # Log activity
                ActivityLog.objects.create(
                    user=current_user,
                    activity_type=ActivityLog.ActivityType.FOLLOW,
                    description=f"Started following {target_user.get_full_name()}",
                    ip_address=get_client_ip(request),
                    user_agent=get_user_agent(request),
                )

            serializer = FollowSerializer(follow_obj, context={"request": request})
            return Response(serializer.data, status=status.HTTP_200_OK)

        else:  # DELETE
            try:
                follow_obj = Follow.objects.get(
                    follower=current_user, following=target_user
                )
                follow_obj.delete()

                # Log activity
                ActivityLog.objects.create(
                    user=current_user,
                    activity_type=ActivityLog.ActivityType.UNFOLLOW,
                    description=f"Unfollowed {target_user.get_full_name()}",
                    ip_address=get_client_ip(request),
                    user_agent=get_user_agent(request),
                )

                return Response(
                    {"message": "Unfollowed successfully"}, status=status.HTTP_200_OK
                )
            except Follow.DoesNotExist:
                return Response(
                    {"error": "Not following this user"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

    @extend_schema(
        summary="Endorse Skill",
        description="Endorse a skill for the user",
        request=SkillEndorseSerializer,
        responses={201: "Skill endorsed successfully"},
    )
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def endorse_skill(self, request: Request, pk=None) -> Response:
        """Endorse a skill for the user"""
        target_user = self.get_object()
        current_user = request.user

        if target_user == current_user:
            return Response(
                {"error": "Cannot endorse your own skills"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = SkillEndorseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        skill_id = serializer.validated_data["skill_id"]

        try:
            skill = Skill.objects.get(id=skill_id, user_profile__user=target_user)
        except Skill.DoesNotExist:
            return Response(
                {"error": "Skill not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Check if already endorsed
        existing_endorsement = SkillEndorsement.objects.filter(
            skill=skill, endorser=current_user
        ).first()

        if existing_endorsement:
            return Response(
                {"error": "Skill already endorsed"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Create endorsement
        SkillEndorsement.objects.create(
            skill=skill,
            endorser=current_user,
            message=serializer.validated_data.get("message", ""),
        )

        # Log activity
        ActivityLog.objects.create(
            user=current_user,
            activity_type=ActivityLog.ActivityType.ENDORSEMENT,
            description=f"Endorsed {skill.name} skill for {target_user.get_full_name()}",
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )

        return Response(
            {"message": "Skill endorsed successfully"}, status=status.HTTP_201_CREATED
        )

    @extend_schema(
        summary="Get Profile Analytics",
        description="Get detailed analytics for user profile (owner only)",
        responses={200: ProfileAnalyticsSerializer},
    )
    @action(
        detail=True,
        methods=["get"],
        permission_classes=[IsAuthenticated, IsProfileOwner],
    )
    def analytics(self, request: Request, pk=None) -> Response:
        """Get profile analytics"""
        user = self.get_object()

        # Get analytics data
        now = timezone.now()
        last_week = now - timedelta(days=7)
        last_month = now - timedelta(days=30)

        analytics_data = {
            "profile_views": {
                "total": ProfileView.objects.filter(viewed=user).aggregate(
                    total=models.Sum("view_count")
                )["total"]
                or 0,
                "this_week": ProfileView.objects.filter(
                    viewed=user, last_viewed__gte=last_week
                ).aggregate(total=models.Sum("view_count"))["total"]
                or 0,
                "this_month": ProfileView.objects.filter(
                    viewed=user, last_viewed__gte=last_month
                ).aggregate(total=models.Sum("view_count"))["total"]
                or 0,
            },
            "connections": {
                "total": Connection.objects.filter(
                    Q(from_user=user) | Q(to_user=user),
                    status=Connection.ConnectionStatus.ACCEPTED,
                ).count(),
                "pending_sent": Connection.objects.filter(
                    from_user=user, status=Connection.ConnectionStatus.PENDING
                ).count(),
                "pending_received": Connection.objects.filter(
                    to_user=user, status=Connection.ConnectionStatus.PENDING
                ).count(),
            },
            "followers": Follow.objects.filter(following=user).count(),
            "following": Follow.objects.filter(follower=user).count(),
            "skill_endorsements": SkillEndorsement.objects.filter(
                skill__user_profile__user=user
            ).count(),
            "profile_completeness": self.calculate_profile_completeness(user),
        }

        return Response(analytics_data)

    def calculate_profile_completeness(self, user: User) -> float:  # type: ignore
        """Calculate profile completeness percentage"""
        if not hasattr(user, "profile"):
            return 0.0

        profile = user.profile
        fields_to_check = [
            profile.bio,
            profile.avatar,
            profile.headline,
            profile.location,
            profile.current_company,
        ]

        completed_fields = sum(1 for field in fields_to_check if field)
        basic_completion = (
            completed_fields / len(fields_to_check)
        ) * 60  # 60% for basic fields

        # Additional sections (40% total)
        additional_completion = 0
        if profile.experience.exists():
            additional_completion += 10
        if profile.education.exists():
            additional_completion += 10
        if profile.skills.exists():
            additional_completion += 10
        if profile.projects.exists():
            additional_completion += 10

        return basic_completion + additional_completion

    @extend_schema(
        summary="Update Online Status",
        description="Update user online status",
        request=OnlineStatusSerializer,
        responses={200: OnlineStatusSerializer},
    )
    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def update_online_status(self, request: Request) -> Response:
        """Update user's online status"""
        serializer = OnlineStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        is_online = serializer.validated_data["is_online"]
        status_type = serializer.validated_data.get("status", "active")

        if hasattr(request.user, "profile"):
            request.user.profile.is_online = is_online
            request.user.profile.status = status_type
            if is_online:
                request.user.profile.update_last_activity()
            request.user.profile.save(
                update_fields=["is_online", "status", "last_activity"]
            )

        return Response({"is_online": is_online, "status": status_type})

    @extend_schema(
        summary="Bulk Operations",
        description="Perform bulk operations on multiple users",
        request=BulkOperationSerializer,
        responses={200: "Bulk operation completed"},
    )
    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def bulk_operations(self, request: Request) -> Response:
        """Perform bulk operations"""
        serializer = BulkOperationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        operation = serializer.validated_data["operation"]
        user_ids = serializer.validated_data["user_ids"]

        # Limit bulk operations to prevent abuse
        if len(user_ids) > 100:
            return Response(
                {"error": "Maximum 100 users allowed per operation"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        users = User.objects.filter(id__in=user_ids)
        current_user = request.user

        if operation == "follow":
            follows_created = 0
            for user in users:
                if user != current_user:
                    _, created = Follow.objects.get_or_create(
                        follower=current_user, following=user
                    )
                    if created:
                        follows_created += 1

            return Response(
                {"message": f"Followed {follows_created} users successfully"}
            )

        elif operation == "connect":
            connections_created = 0
            for user in users:
                if user != current_user:
                    _, created = Connection.objects.get_or_create(
                        from_user=current_user,
                        to_user=user,
                        defaults={"status": Connection.ConnectionStatus.PENDING},
                    )
                    if created:
                        connections_created += 1

            return Response(
                {"message": f"Sent {connections_created} connection requests"}
            )

        else:
            return Response(
                {"error": "Invalid operation"}, status=status.HTTP_400_BAD_REQUEST
            )

    @extend_schema(
        summary="Get Activity Log",
        description="Get user activity log (owner only)",
        responses={200: "Activity log data"},
    )
    @action(
        detail=True,
        methods=["get"],
        permission_classes=[IsAuthenticated, IsProfileOwner],
    )
    def activity_log(self, request: Request, pk=None) -> Response:
        """Get user's activity log"""
        user = self.get_object()

        logs = ActivityLog.objects.filter(user=user).order_by("-created_at")[:50]

        log_data = []
        for log in logs:
            log_data.append(
                {
                    "id": log.id,
                    "activity_type": log.activity_type,
                    "description": log.description,
                    "created_at": log.created_at,
                    "ip_address": log.ip_address,
                    "metadata": log.metadata,
                }
            )

        return Response(log_data)

    @extend_schema(
        summary="Get Connections Data",
        description="Get detailed connections data (owner only)",
        responses={200: "Connections data"},
    )
    @action(
        detail=True,
        methods=["get"],
        permission_classes=[IsAuthenticated, IsProfileOwner],
    )
    def connections_data(self, request: Request, pk=None) -> Response:
        """Get detailed connections data"""
        user = self.get_object()

        connections = Connection.objects.filter(
            Q(from_user=user) | Q(to_user=user)
        ).select_related("from_user", "to_user")

        data = {
            "accepted": [],
            "pending_sent": [],
            "pending_received": [],
            "rejected": [],
        }

        for connection in connections:
            other_user = (
                connection.to_user
                if connection.from_user == user
                else connection.from_user
            )
            connection_data = {
                "id": connection.id,
                "user": UserBasicSerializer(other_user).data,
                "created_at": connection.created_at,
                "status": connection.status,
            }

            if connection.status == Connection.ConnectionStatus.ACCEPTED:
                data["accepted"].append(connection_data)
            elif connection.status == Connection.ConnectionStatus.PENDING:
                if connection.from_user == user:
                    data["pending_sent"].append(connection_data)
                else:
                    data["pending_received"].append(connection_data)
            elif connection.status == Connection.ConnectionStatus.REJECTED:
                data["rejected"].append(connection_data)

        return Response(data)
