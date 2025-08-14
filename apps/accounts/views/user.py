import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from ..models import (
    ActivityLog,
    Connection,
    Follow,
    Message,
    Notification,
    ProfileStats,
    ProfileView,
    Skill,
    SkillEndorsement,
    UserFile,
    UserProfile,
)
from ..permissions import (
    IsAdminUser,
    IsOwnerOrAdmin,
    can_endorse_skill,
    can_send_connection_request,
    can_send_message,
    can_view_user_profile,
)
from ..serializers import (
    AccountSettingsSerializer,
    ActivityLogSerializer,
    ConnectionRequestSerializer,
    ConnectionSerializer,
    CoverImageUploadSerializer,
    FileUploadSerializer,
    FollowSerializer,
    MessageSerializer,
    NotificationSerializer,
    OnlineStatusSerializer,
    PasswordChangeSerializer,
    PrivacySettingsSerializer,
    ProfileAnalyticsSerializer,
    ProfilePictureUploadSerializer,
    ProfileSearchSerializer,
    ProfileSettingsSerializer,
    RegisterSerializer,
    SkillEndorsementSerializer,
    SkillEndorseSerializer,
    StatusUpdateSerializer,
    UserBasicSerializer,
    UserFileSerializer,
    UserProfileSerializer,
    UserSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
                "page": self.page.number,
                "total_pages": self.page.paginator.num_pages,
            }
        )


class UserThrottle(UserRateThrottle):
    rate = "1000/hour"


class UserViewSet(viewsets.ModelViewSet):
    """
    Comprehensive user management with professional networking features.
    """

    queryset = (
        User.objects.select_related("profile", "stats")
        .prefetch_related(
            "social_links",
            "experiences",
            "educations",
            "certifications",
            "projects",
            "skills",
            "languages",
            "achievements",
            "publications",
            "volunteer_work",
            "files",
        )
        .order_by("username")
    )

    serializer_class = UserSerializer
    pagination_class = StandardResultsSetPagination
    throttle_classes = [UserThrottle]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = [
        "is_active",
        "is_staff",
        "is_verified",
        "status",
        "current_company",
        "location",
    ]
    search_fields = [
        "username",
        "email",
        "first_name",
        "last_name",
        "headline",
        "current_position",
        "current_company",
        "location",
        "bio",
    ]
    ordering_fields = [
        "username",
        "email",
        "date_joined",
        "last_activity",
        "first_name",
        "last_name",
    ]
    ordering = ["username"]

    def get_permissions(self):
        if self.action in ["list", "retrieve", "search_profiles"]:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ["create", "destroy", "bulk_delete"]:
            permission_classes = [permissions.IsAuthenticated, IsAdminUser]
        elif self.action in ["update", "partial_update"]:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        elif self.action in [
            "upload_profile_picture",
            "upload_cover_image",
            "update_status",
            "change_password",
            "change_email",
            "change_username",
            "update_settings",
        ]:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        elif self.action in [
            "connect",
            "disconnect",
            "follow",
            "unfollow",
            "endorse_skill",
            "send_message",
        ]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, IsAdminUser]
        return [permission() for permission in permission_classes]

    def get_serializer_class(self):
        if self.action == "create":
            return RegisterSerializer
        elif self.action in ["list", "connections", "followers", "following"]:
            return UserBasicSerializer
        elif self.action == "search_profiles":
            return UserSerializer
        elif self.action == "analytics":
            return ProfileAnalyticsSerializer
        return UserSerializer

    def get_queryset(self):
        """Filter queryset based on permissions and visibility."""
        queryset = super().get_queryset()

        if self.action == "list":
            # Only show public profiles or connected users
            if not self.request.user.is_staff:
                # Get connected user IDs
                connected_users = Connection.objects.filter(
                    Q(from_user=self.request.user) | Q(to_user=self.request.user),
                    status=Connection.ConnectionStatus.ACCEPTED,
                ).values_list("from_user_id", "to_user_id")

                connected_ids = set()
                for from_id, to_id in connected_users:
                    connected_ids.add(from_id)
                    connected_ids.add(to_id)
                connected_ids.discard(self.request.user.id)

                # Filter for public profiles or connected users
                queryset = queryset.filter(
                    Q(profile__profile_visibility="public")
                    | Q(id__in=connected_ids)
                    | Q(id=self.request.user.id)
                )

        return queryset

    def retrieve(self, request, *args, **kwargs):
        """Retrieve user profile with view tracking."""
        try:
            instance = self.get_object()

            # Check if user can view this profile
            if not can_view_user_profile(request.user, instance):
                raise PermissionDenied("You don't have permission to view this profile")

            # Track profile view
            if request.user != instance:
                ProfileView.objects.get_or_create(
                    viewer=request.user,
                    profile_owner=instance,
                    defaults={
                        "ip_address": request.META.get("REMOTE_ADDR"),
                        "user_agent": request.META.get("HTTP_USER_AGENT", ""),
                        "referrer": request.META.get("HTTP_REFERER", ""),
                    },
                )

                # Update profile stats
                stats, created = ProfileStats.objects.get_or_create(user=instance)
                stats.profile_views += 1

                # Update weekly and monthly views
                now = timezone.now()
                week_ago = now - timedelta(days=7)
                month_ago = now - timedelta(days=30)

                stats.profile_views_this_week = ProfileView.objects.filter(
                    profile_owner=instance, created_at__gte=week_ago
                ).count()

                stats.profile_views_this_month = ProfileView.objects.filter(
                    profile_owner=instance, created_at__gte=month_ago
                ).count()

                stats.save()

            serializer = self.get_serializer(instance)
            logger.info(
                f"Profile viewed: {instance.username} by {request.user.username}"
            )
            return Response(serializer.data)

        except PermissionDenied:
            raise
        except Exception as e:
            logger.error(f"Error retrieving user profile: {str(e)}", exc_info=True)
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User Profiles"],
        parameters=[
            OpenApiParameter("query", OpenApiTypes.STR, description="Search query"),
            OpenApiParameter(
                "skills", OpenApiTypes.STR, description="Comma-separated skills"
            ),
            OpenApiParameter(
                "location", OpenApiTypes.STR, description="Location filter"
            ),
            OpenApiParameter("company", OpenApiTypes.STR, description="Company filter"),
            OpenApiParameter("page", OpenApiTypes.INT, description="Page number"),
            OpenApiParameter("limit", OpenApiTypes.INT, description="Results per page"),
        ],
        responses={200: UserSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def search_profiles(self, request):
        """Advanced profile search with filters."""
        try:
            search_serializer = ProfileSearchSerializer(data=request.query_params)
            search_serializer.is_valid(raise_exception=True)

            params = search_serializer.validated_data
            queryset = self.get_queryset()

            # Apply search filters
            if params.get("query"):
                query = params["query"]
                queryset = queryset.filter(
                    Q(username__icontains=query)
                    | Q(first_name__icontains=query)
                    | Q(last_name__icontains=query)
                    | Q(headline__icontains=query)
                    | Q(current_position__icontains=query)
                    | Q(current_company__icontains=query)
                    | Q(bio__icontains=query)
                )

            if params.get("skills"):
                queryset = queryset.filter(skills__name__in=params["skills"]).distinct()

            if params.get("location"):
                queryset = queryset.filter(location__icontains=params["location"])

            if params.get("company"):
                queryset = queryset.filter(current_company__icontains=params["company"])

            # Apply sorting
            sort_by = params.get("sort_by", "relevance")
            sort_order = params.get("sort_order", "desc")

            if sort_by == "name":
                order_field = "first_name" if sort_order == "asc" else "-first_name"
            elif sort_by == "experience":
                order_field = "date_joined" if sort_order == "asc" else "-date_joined"
            elif sort_by == "connections":
                # Annotate with connection count
                queryset = queryset.annotate(
                    connection_count=Count(
                        "connections_sent",
                        filter=Q(connections_sent__status="accepted"),
                    )
                    + Count(
                        "connections_received",
                        filter=Q(connections_received__status="accepted"),
                    )
                )
                order_field = (
                    "connection_count" if sort_order == "asc" else "-connection_count"
                )
            else:  # relevance
                order_field = "-last_activity"

            queryset = queryset.order_by(order_field)

            # Paginate results
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error in profile search: {str(e)}", exc_info=True)
            return Response(
                {"error": "Search failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User Profiles"],
        request=ConnectionRequestSerializer,
        responses={201: ConnectionSerializer},
    )
    @action(detail=True, methods=["post"])
    def connect(self, request, pk=None):
        """Send connection request to another user."""
        try:
            target_user = self.get_object()

            if not can_send_connection_request(request.user, target_user):
                return Response(
                    {"error": "Cannot send connection request to this user"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            serializer = ConnectionRequestSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            connection = Connection.objects.create(
                from_user=request.user,
                to_user=target_user,
                message=serializer.validated_data.get("message", ""),
                status=Connection.ConnectionStatus.PENDING,
            )

            # Create notification
            Notification.objects.create(
                recipient=target_user,
                sender=request.user,
                notification_type=Notification.NotificationType.CONNECTION_REQUEST,
                title=f"Connection request from {request.user.get_full_name()}",
                message=f"{request.user.get_full_name()} wants to connect with you.",
                data={"connection_id": str(connection.id)},
            )

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                activity_type=ActivityLog.ActivityType.CONNECTION_REQUEST,
                description=f"Sent connection request to {target_user.get_full_name()}",
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )

            logger.info(
                f"Connection request sent from {request.user.username} to {target_user.username}"
            )
            return Response(
                ConnectionSerializer(connection).data,
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.error(f"Error sending connection request: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to send connection request"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User Profiles"],
        responses={204: None},
    )
    @action(detail=True, methods=["delete"])
    def disconnect(self, request, pk=None):
        """Remove connection with another user."""
        try:
            target_user = self.get_object()

            connection = Connection.objects.filter(
                Q(from_user=request.user, to_user=target_user)
                | Q(from_user=target_user, to_user=request.user),
                status=Connection.ConnectionStatus.ACCEPTED,
            ).first()

            if not connection:
                return Response(
                    {"error": "No connection exists with this user"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            connection.delete()

            # Update connection counts
            for user in [request.user, target_user]:
                stats, created = ProfileStats.objects.get_or_create(user=user)
                stats.connections_count = Connection.objects.filter(
                    Q(from_user=user) | Q(to_user=user),
                    status=Connection.ConnectionStatus.ACCEPTED,
                ).count()
                stats.save()

            logger.info(
                f"Connection removed between {request.user.username} and {target_user.username}"
            )
            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception as e:
            logger.error(f"Error removing connection: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to remove connection"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User Profiles"],
        responses={201: FollowSerializer},
    )
    @action(detail=True, methods=["post"])
    def follow(self, request, pk=None):
        """Follow another user."""
        try:
            target_user = self.get_object()

            if request.user == target_user:
                return Response(
                    {"error": "Cannot follow yourself"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            follow_obj, created = Follow.objects.get_or_create(
                follower=request.user,
                following=target_user,
            )

            if not created:
                return Response(
                    {"error": "Already following this user"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Create notification
            Notification.objects.create(
                recipient=target_user,
                sender=request.user,
                notification_type=Notification.NotificationType.CONNECTION_REQUEST,
                title=f"{request.user.get_full_name()} is now following you",
                message=f"{request.user.get_full_name()} started following you.",
            )

            logger.info(
                f"{request.user.username} started following {target_user.username}"
            )
            return Response(
                FollowSerializer(follow_obj).data,
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.error(f"Error following user: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to follow user"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User Profiles"],
        responses={204: None},
    )
    @action(detail=True, methods=["delete"])
    def unfollow(self, request, pk=None):
        """Unfollow another user."""
        try:
            target_user = self.get_object()

            follow_obj = Follow.objects.filter(
                follower=request.user,
                following=target_user,
            ).first()

            if not follow_obj:
                return Response(
                    {"error": "Not following this user"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            follow_obj.delete()

            logger.info(f"{request.user.username} unfollowed {target_user.username}")
            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception as e:
            logger.error(f"Error unfollowing user: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to unfollow user"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User Profiles"],
        responses={200: UserBasicSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def connections(self, request, pk=None):
        """Get user's connections."""
        try:
            user = self.get_object()

            if not can_view_user_profile(request.user, user):
                raise PermissionDenied("You don't have permission to view connections")

            connections = Connection.objects.filter(
                Q(from_user=user) | Q(to_user=user),
                status=Connection.ConnectionStatus.ACCEPTED,
            ).select_related("from_user", "to_user")

            connected_users = []
            for conn in connections:
                other_user = conn.to_user if conn.from_user == user else conn.from_user
                connected_users.append(other_user)

            page = self.paginate_queryset(connected_users)
            if page is not None:
                serializer = UserBasicSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = UserBasicSerializer(connected_users, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error getting connections: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get connections"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User Profiles"],
        responses={200: UserBasicSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def followers(self, request, pk=None):
        """Get user's followers."""
        try:
            user = self.get_object()

            if not can_view_user_profile(request.user, user):
                raise PermissionDenied("You don't have permission to view followers")

            followers_qs = user.followers.all().select_related("follower")
            followers = [follow.follower for follow in followers_qs]

            page = self.paginate_queryset(followers)
            if page is not None:
                serializer = UserBasicSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = UserBasicSerializer(followers, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error getting followers: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get followers"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User Profiles"],
        responses={200: UserBasicSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def following(self, request, pk=None):
        """Get users that this user is following."""
        try:
            user = self.get_object()

            if not can_view_user_profile(request.user, user):
                raise PermissionDenied("You don't have permission to view following")

            following_qs = user.following.all().select_related("following")
            following = [follow.following for follow in following_qs]

            page = self.paginate_queryset(following)
            if page is not None:
                serializer = UserBasicSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = UserBasicSerializer(following, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error getting following: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get following"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Skills"],
        request=SkillEndorseSerializer,
        responses={201: SkillEndorsementSerializer},
    )
    @action(detail=True, methods=["post"])
    def endorse_skill(self, request, pk=None):
        """Endorse a user's skill."""
        try:
            skill_owner = self.get_object()

            if not can_endorse_skill(request.user, skill_owner):
                return Response(
                    {"error": "Cannot endorse skills for this user"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            serializer = SkillEndorseSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            skill_id = serializer.validated_data["skill_id"]
            message = serializer.validated_data.get("message", "")

            skill = Skill.objects.filter(id=skill_id, user=skill_owner).first()
            if not skill:
                return Response(
                    {"error": "Skill not found"},
                    status=status.HTTP_404_NOT_FOUND,
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
                message=message,
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

            logger.info(f"Skill endorsed: {skill.name} by {request.user.username}")
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
        tags=["Messaging"],
        request=MessageSerializer,
        responses={201: MessageSerializer},
    )
    @action(detail=True, methods=["post"])
    def send_message(self, request, pk=None):
        """Send a message to another user."""
        try:
            recipient = self.get_object()

            if not can_send_message(request.user, recipient):
                return Response(
                    {"error": "Cannot send message to this user"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            serializer = MessageSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            message = Message.objects.create(
                sender=request.user,
                recipient=recipient,
                subject=serializer.validated_data.get("subject", ""),
                content=serializer.validated_data["content"],
                attachment=serializer.validated_data.get("attachment"),
            )

            # Create notification
            Notification.objects.create(
                recipient=recipient,
                sender=request.user,
                notification_type=Notification.NotificationType.MESSAGE,
                title=f"New message from {request.user.get_full_name()}",
                message=f"You have a new message from {request.user.get_full_name()}.",
                data={"message_id": str(message.id)},
            )

            logger.info(
                f"Message sent from {request.user.username} to {recipient.username}"
            )
            return Response(
                MessageSerializer(message).data,
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.error(f"Error sending message: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to send message"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User Profiles"],
        request=StatusUpdateSerializer,
        responses={200: OnlineStatusSerializer},
    )
    @action(detail=False, methods=["post"])
    def update_status(self, request):
        """Update user's online status."""
        try:
            serializer = StatusUpdateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            request.user.status = serializer.validated_data["status"]
            request.user.save(update_fields=["status"])

            return Response(
                OnlineStatusSerializer(
                    {
                        "is_online": request.user.is_online,
                        "last_seen": request.user.last_activity,
                    }
                ).data
            )

        except Exception as e:
            logger.error(f"Error updating status: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to update status"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User Management"],
        request=ProfilePictureUploadSerializer,
        responses={200: UserSerializer},
    )
    @action(
        detail=False, methods=["post"], parser_classes=[MultiPartParser, FormParser]
    )
    def upload_profile_picture(self, request):
        """Upload profile picture."""
        try:
            serializer = ProfilePictureUploadSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            request.user.profile_picture = serializer.validated_data["profile_picture"]
            request.user.save(update_fields=["profile_picture"])

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
                description="Updated profile picture",
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            return Response(UserSerializer(request.user).data)

        except Exception as e:
            logger.error(f"Error uploading profile picture: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to upload profile picture"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User Management"],
        request=CoverImageUploadSerializer,
        responses={200: UserProfileSerializer},
    )
    @action(
        detail=False, methods=["post"], parser_classes=[MultiPartParser, FormParser]
    )
    def upload_cover_image(self, request):
        """Upload cover image."""
        try:
            serializer = CoverImageUploadSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            profile, created = UserProfile.objects.get_or_create(user=request.user)
            profile.cover_image = serializer.validated_data["cover_image"]
            profile.save(update_fields=["cover_image"])

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
                description="Updated cover image",
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            return Response(UserProfileSerializer(profile).data)

        except Exception as e:
            logger.error(f"Error uploading cover image: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to upload cover image"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User Management"],
        request=PasswordChangeSerializer,
        responses={200: {"message": "Password changed successfully"}},
    )
    @action(detail=False, methods=["post"])
    def change_password(self, request):
        """Change user password."""
        try:
            serializer = PasswordChangeSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            if not request.user.check_password(
                serializer.validated_data["old_password"]
            ):
                return Response(
                    {"error": "Current password is incorrect"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            request.user.set_password(serializer.validated_data["new_password"])
            request.user.save()

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                activity_type=ActivityLog.ActivityType.PASSWORD_CHANGE,
                description="Password changed",
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            return Response({"message": "Password changed successfully"})

        except Exception as e:
            logger.error(f"Error changing password: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to change password"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User Profiles"],
        responses={200: ProfileAnalyticsSerializer},
    )
    @action(detail=True, methods=["get"])
    def analytics(self, request, pk=None):
        """Get user profile analytics."""
        try:
            user = self.get_object()

            # Only allow users to view their own analytics or admins
            if request.user != user and not request.user.is_staff:
                raise PermissionDenied("You can only view your own analytics")

            # Get profile views data
            now = timezone.now()
            thirty_days_ago = now - timedelta(days=30)

            profile_views = (
                ProfileView.objects.filter(
                    profile_owner=user, created_at__gte=thirty_days_ago
                )
                .values("created_at__date")
                .annotate(count=Count("id"))
                .order_by("created_at__date")
            )

            # Get connection growth
            connections = (
                Connection.objects.filter(
                    Q(from_user=user) | Q(to_user=user),
                    status=Connection.ConnectionStatus.ACCEPTED,
                    created_at__gte=thirty_days_ago,
                )
                .values("created_at__date")
                .annotate(count=Count("id"))
                .order_by("created_at__date")
            )

            # Get skill endorsements
            endorsements = (
                SkillEndorsement.objects.filter(
                    skill__user=user, created_at__gte=thirty_days_ago
                )
                .values("created_at__date")
                .annotate(count=Count("id"))
                .order_by("created_at__date")
            )

            # Get top viewers
            top_viewers = (
                ProfileView.objects.filter(
                    profile_owner=user,
                    viewer__isnull=False,
                    created_at__gte=thirty_days_ago,
                )
                .values("viewer")
                .annotate(view_count=Count("id"))
                .order_by("-view_count")[:10]
            )

            top_viewer_users = User.objects.filter(
                id__in=[v["viewer"] for v in top_viewers]
            )

            # Get recent activities
            recent_activities = ActivityLog.objects.filter(user=user).order_by(
                "-created_at"
            )[:20]

            analytics_data = {
                "profile_views_data": {
                    "daily_views": list(profile_views),
                    "total_views": (
                        user.stats.profile_views if hasattr(user, "stats") else 0
                    ),
                },
                "connection_growth": {
                    "daily_connections": list(connections),
                    "total_connections": (
                        user.stats.connections_count if hasattr(user, "stats") else 0
                    ),
                },
                "skill_endorsements_data": {
                    "daily_endorsements": list(endorsements),
                    "total_endorsements": (
                        user.stats.endorsements_count if hasattr(user, "stats") else 0
                    ),
                },
                "search_appearances_data": {
                    "total_appearances": (
                        user.stats.search_appearances if hasattr(user, "stats") else 0
                    ),
                },
                "top_viewers": UserBasicSerializer(top_viewer_users, many=True).data,
                "recent_activities": ActivityLogSerializer(
                    recent_activities, many=True
                ).data,
            }

            return Response(analytics_data)

        except Exception as e:
            logger.error(f"Error getting analytics: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get analytics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User Management"],
        request=ProfileSettingsSerializer,
        responses={200: UserProfileSerializer},
    )
    @action(detail=False, methods=["post"])
    def update_settings(self, request):
        """Update user profile settings."""
        try:
            profile, created = UserProfile.objects.get_or_create(user=request.user)

            # Handle different types of settings updates
            if "profile_visibility" in request.data:
                profile_settings = ProfileSettingsSerializer(data=request.data)
                profile_settings.is_valid(raise_exception=True)

                for field, value in profile_settings.validated_data.items():
                    setattr(profile, field, value)

            elif "theme" in request.data:
                account_settings = AccountSettingsSerializer(data=request.data)
                account_settings.is_valid(raise_exception=True)

                for field, value in account_settings.validated_data.items():
                    setattr(profile, field, value)

            elif "data_processing" in request.data:
                privacy_settings = PrivacySettingsSerializer(data=request.data)
                privacy_settings.is_valid(raise_exception=True)

                for field, value in privacy_settings.validated_data.items():
                    setattr(profile, field, value)

            profile.save()

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
                description="Updated profile settings",
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            return Response(UserProfileSerializer(profile).data)

        except Exception as e:
            logger.error(f"Error updating settings: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to update settings"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Files"],
        request=FileUploadSerializer,
        responses={201: UserFileSerializer},
    )
    @action(
        detail=False, methods=["post"], parser_classes=[MultiPartParser, FormParser]
    )
    def upload_file(self, request):
        """Upload a file (resume, portfolio, etc.)."""
        try:
            serializer = FileUploadSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            user_file = UserFile.objects.create(
                user=request.user, **serializer.validated_data
            )

            return Response(
                UserFileSerializer(user_file).data,
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.error(f"Error uploading file: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to upload file"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User Management"],
        responses={200: UserBasicSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def suggestions(self, request):
        """Get user connection suggestions based on mutual connections, skills, etc."""
        try:
            # Get users with mutual connections
            user_connections = Connection.objects.filter(
                Q(from_user=request.user) | Q(to_user=request.user),
                status=Connection.ConnectionStatus.ACCEPTED,
            )

            connected_user_ids = set()
            for conn in user_connections:
                other_user = (
                    conn.to_user if conn.from_user == request.user else conn.from_user
                )
                connected_user_ids.add(other_user.id)

            # Find users connected to my connections but not to me
            mutual_connections = Connection.objects.filter(
                Q(from_user_id__in=connected_user_ids)
                | Q(to_user_id__in=connected_user_ids),
                status=Connection.ConnectionStatus.ACCEPTED,
            ).exclude(Q(from_user=request.user) | Q(to_user=request.user))

            suggested_user_ids = set()
            for conn in mutual_connections:
                if conn.from_user_id not in connected_user_ids:
                    suggested_user_ids.add(conn.from_user_id)
                if conn.to_user_id not in connected_user_ids:
                    suggested_user_ids.add(conn.to_user_id)

            # Also suggest users with similar skills
            user_skills = Skill.objects.filter(user=request.user).values_list(
                "name", flat=True
            )
            if user_skills:
                similar_skill_users = (
                    Skill.objects.filter(name__in=user_skills)
                    .exclude(user=request.user)
                    .exclude(user_id__in=connected_user_ids)
                    .values_list("user_id", flat=True)
                )

                suggested_user_ids.update(similar_skill_users)

            # Get suggested users
            suggested_users = User.objects.filter(
                id__in=suggested_user_ids,
                is_active=True,
                profile__profile_visibility="public",
            )[:20]

            serializer = UserBasicSerializer(suggested_users, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error getting suggestions: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get suggestions"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Connections"],
        responses={200: ConnectionSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def connection_requests(self, request):
        """Get pending connection requests."""
        try:
            pending_requests = (
                Connection.objects.filter(
                    to_user=request.user,
                    status=Connection.ConnectionStatus.PENDING,
                )
                .select_related("from_user")
                .order_by("-created_at")
            )

            page = self.paginate_queryset(pending_requests)
            if page is not None:
                serializer = ConnectionSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = ConnectionSerializer(pending_requests, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error getting connection requests: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get connection requests"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Connections"],
        responses={200: ConnectionSerializer},
    )
    @action(detail=True, methods=["post"], url_path="accept-connection")
    def accept_connection(self, request, pk=None):
        """Accept a connection request."""
        try:
            connection = Connection.objects.filter(
                id=pk,
                to_user=request.user,
                status=Connection.ConnectionStatus.PENDING,
            ).first()

            if not connection:
                return Response(
                    {"error": "Connection request not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            connection.status = Connection.ConnectionStatus.ACCEPTED
            connection.save()

            # Update connection counts for both users
            for user in [connection.from_user, connection.to_user]:
                stats, created = ProfileStats.objects.get_or_create(user=user)
                stats.connections_count = Connection.objects.filter(
                    Q(from_user=user) | Q(to_user=user),
                    status=Connection.ConnectionStatus.ACCEPTED,
                ).count()
                stats.save()

            # Create notification
            Notification.objects.create(
                recipient=connection.from_user,
                sender=request.user,
                notification_type=Notification.NotificationType.CONNECTION_ACCEPTED,
                title=f"{request.user.get_full_name()} accepted your connection request",
                message=f"{request.user.get_full_name()} is now connected with you.",
                data={"connection_id": str(connection.id)},
            )

            logger.info(
                f"Connection accepted: {connection.from_user.username} <-> {connection.to_user.username}"
            )
            return Response(ConnectionSerializer(connection).data)

        except Exception as e:
            logger.error(f"Error accepting connection: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to accept connection"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Connections"],
        responses={204: None},
    )
    @action(detail=True, methods=["post"], url_path="decline-connection")
    def decline_connection(self, request, pk=None):
        """Decline a connection request."""
        try:
            connection = Connection.objects.filter(
                id=pk,
                to_user=request.user,
                status=Connection.ConnectionStatus.PENDING,
            ).first()

            if not connection:
                return Response(
                    {"error": "Connection request not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            connection.status = Connection.ConnectionStatus.DECLINED
            connection.save()

            logger.info(
                f"Connection declined: {connection.from_user.username} -> {connection.to_user.username}"
            )
            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception as e:
            logger.error(f"Error declining connection: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to decline connection"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Notifications"],
        responses={200: NotificationSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def notifications(self, request):
        """Get user notifications."""
        try:
            notifications = (
                Notification.objects.filter(recipient=request.user)
                .select_related("sender")
                .order_by("-created_at")
            )

            page = self.paginate_queryset(notifications)
            if page is not None:
                serializer = NotificationSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = NotificationSerializer(notifications, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error getting notifications: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get notifications"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Notifications"],
        responses={200: NotificationSerializer},
    )
    @action(detail=True, methods=["post"], url_path="mark-notification-read")
    def mark_notification_read(self, request, pk=None):
        """Mark a notification as read."""
        try:
            notification = Notification.objects.filter(
                id=pk,
                recipient=request.user,
            ).first()

            if not notification:
                return Response(
                    {"error": "Notification not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            notification.mark_as_read()
            return Response(NotificationSerializer(notification).data)

        except Exception as e:
            logger.error(f"Error marking notification as read: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to mark notification as read"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Messages"],
        responses={200: MessageSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def messages(self, request):
        """Get user messages."""
        try:
            messages = (
                Message.objects.filter(
                    Q(sender=request.user) | Q(recipient=request.user)
                )
                .select_related("sender", "recipient")
                .order_by("-created_at")
            )

            page = self.paginate_queryset(messages)
            if page is not None:
                serializer = MessageSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = MessageSerializer(messages, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error getting messages: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get messages"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
