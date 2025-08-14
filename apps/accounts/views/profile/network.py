import logging

from django.contrib.auth import get_user_model
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from ...models import ActivityLog, Network, NetworkMembership, Notification
from ...permissions import IsNetworkAdmin
from ...serializers import (
    NetworkMembershipSerializer,
    NetworkSerializer,
    UserBasicSerializer,
)
from ..user import StandardResultsSetPagination, UserThrottle

logger = logging.getLogger(__name__)
User = get_user_model()


class NetworkViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing professional networks and communities.
    """

    serializer_class = NetworkSerializer
    pagination_class = StandardResultsSetPagination
    throttle_classes = [UserThrottle]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["industry", "location", "is_verified", "is_public"]
    search_fields = ["name", "description", "industry", "location"]
    ordering_fields = ["name", "member_count", "created_at"]
    ordering = ["-member_count"]

    def get_queryset(self):
        """Filter networks based on visibility and permissions."""
        user = self.request.user

        if self.action == "list":
            # Show public networks and networks user is a member of
            if user.is_staff:
                return Network.objects.all().select_related("created_by")
            else:
                user_networks = NetworkMembership.objects.filter(
                    user=user, status=NetworkMembership.MembershipStatus.ACTIVE
                ).values_list("network_id", flat=True)

                return Network.objects.filter(
                    Q(is_public=True) | Q(id__in=user_networks)
                ).select_related("created_by")

        elif self.action in ["my_networks", "administered"]:
            return (
                Network.objects.filter(Q(created_by=user) | Q(admins=user))
                .distinct()
                .select_related("created_by")
            )

        return Network.objects.all().select_related("created_by")

    def get_permissions(self):
        if self.action in ["list", "retrieve", "search", "popular"]:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ["create"]:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ["update", "partial_update", "destroy"]:
            permission_classes = [permissions.IsAuthenticated, IsNetworkAdmin]
        elif self.action in ["join", "leave", "invite_user"]:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in [
            "approve_membership",
            "reject_membership",
            "remove_member",
        ]:
            permission_classes = [permissions.IsAuthenticated, IsNetworkAdmin]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        """Create network and set creator as admin."""
        network = serializer.save(created_by=self.request.user)

        # Add creator as admin
        network.admins.add(self.request.user)

        # Create membership for creator
        NetworkMembership.objects.create(
            user=self.request.user,
            network=network,
            status=NetworkMembership.MembershipStatus.ACTIVE,
            role="admin",
        )

        # Update member count
        network.member_count = 1
        network.save()

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Created network: {network.name}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    @extend_schema(
        tags=["Networks"],
        responses={200: NetworkSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        """List networks with filtering and search."""
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error listing networks: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get networks"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Networks"],
        responses={200: NetworkSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def my_networks(self, request):
        """Get networks where user is a member."""
        try:
            user_memberships = NetworkMembership.objects.filter(
                user=request.user,
                status=NetworkMembership.MembershipStatus.ACTIVE,
            ).select_related("network")

            networks = [membership.network for membership in user_memberships]

            page = self.paginate_queryset(networks)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(networks, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error getting user networks: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get user networks"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Networks"],
        responses={200: NetworkSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def administered(self, request):
        """Get networks administered by the user."""
        try:
            networks = Network.objects.filter(
                Q(created_by=request.user) | Q(admins=request.user)
            ).distinct()

            page = self.paginate_queryset(networks)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(networks, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(
                f"Error getting administered networks: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get administered networks"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Networks"],
        responses={200: NetworkSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def popular(self, request):
        """Get popular networks by member count."""
        try:
            popular_networks = (
                self.get_queryset()
                .filter(is_public=True)
                .order_by("-member_count")[:20]
            )

            serializer = self.get_serializer(popular_networks, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error getting popular networks: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get popular networks"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Networks"],
        responses={201: NetworkMembershipSerializer},
    )
    @action(detail=True, methods=["post"])
    def join(self, request, pk=None):
        """Join a network."""
        try:
            network = self.get_object()

            # Check if already a member
            existing_membership = NetworkMembership.objects.filter(
                user=request.user,
                network=network,
            ).first()

            if existing_membership:
                if (
                    existing_membership.status
                    == NetworkMembership.MembershipStatus.ACTIVE
                ):
                    return Response(
                        {"error": "Already a member of this network"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                elif (
                    existing_membership.status
                    == NetworkMembership.MembershipStatus.BANNED
                ):
                    return Response(
                        {"error": "You are banned from this network"},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                else:
                    # Reactivate membership
                    existing_membership.status = (
                        NetworkMembership.MembershipStatus.PENDING
                    )
                    existing_membership.save()
                    membership = existing_membership
            else:
                # Create new membership
                membership = NetworkMembership.objects.create(
                    user=request.user,
                    network=network,
                    status=NetworkMembership.MembershipStatus.PENDING,
                )

            # For public networks, auto-approve
            if network.is_public:
                membership.status = NetworkMembership.MembershipStatus.ACTIVE
                membership.save()

                # Update member count
                network.member_count = NetworkMembership.objects.filter(
                    network=network,
                    status=NetworkMembership.MembershipStatus.ACTIVE,
                ).count()
                network.save()

            # Notify network admins
            for admin in network.admins.all():
                if admin != request.user:
                    Notification.objects.create(
                        recipient=admin,
                        sender=request.user,
                        notification_type=Notification.NotificationType.NETWORK_INVITATION,
                        title=f"New member request for {network.name}",
                        message=f"{request.user.get_full_name()} wants to join {network.name}.",
                        data={
                            "network_id": str(network.id),
                            "membership_id": str(membership.id),
                        },
                    )

            # Log activity
            ActivityLog.objects.create(
                user=self.request.user,
                activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
                description=f"Joined network: {network.name}",
                ip_address=self.request.META.get("REMOTE_ADDR"),
            )

            return Response(
                NetworkMembershipSerializer(membership).data,
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.error(f"Error joining network: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to join network"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Networks"],
        responses={204: None},
    )
    @action(detail=True, methods=["delete"])
    def leave(self, request, pk=None):
        """Leave a network."""
        try:
            network = self.get_object()

            membership = NetworkMembership.objects.filter(
                user=request.user,
                network=network,
                status=NetworkMembership.MembershipStatus.ACTIVE,
            ).first()

            if not membership:
                return Response(
                    {"error": "You are not a member of this network"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Don't allow creator to leave their own network
            if network.created_by == request.user:
                return Response(
                    {"error": "Network creator cannot leave the network"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            membership.delete()

            # Update member count
            network.member_count = NetworkMembership.objects.filter(
                network=network,
                status=NetworkMembership.MembershipStatus.ACTIVE,
            ).count()
            network.save()

            # Remove from admins if applicable
            if request.user in network.admins.all():
                network.admins.remove(request.user)

            # Log activity
            ActivityLog.objects.create(
                user=self.request.user,
                activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
                description=f"Left network: {network.name}",
                ip_address=self.request.META.get("REMOTE_ADDR"),
            )

            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception as e:
            logger.error(f"Error leaving network: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to leave network"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Networks"],
        responses={200: UserBasicSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def members(self, request, pk=None):
        """Get network members."""
        try:
            network = self.get_object()

            # Check if user can view members
            if not network.is_public:
                membership = NetworkMembership.objects.filter(
                    user=request.user,
                    network=network,
                    status=NetworkMembership.MembershipStatus.ACTIVE,
                ).first()

                if not membership and not request.user.is_staff:
                    raise PermissionDenied(
                        "You must be a member to view network members"
                    )

            memberships = (
                NetworkMembership.objects.filter(
                    network=network,
                    status=NetworkMembership.MembershipStatus.ACTIVE,
                )
                .select_related("user")
                .order_by("-joined_at")
            )

            members = [membership.user for membership in memberships]

            page = self.paginate_queryset(members)
            if page is not None:
                serializer = UserBasicSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = UserBasicSerializer(members, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error getting network members: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get network members"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Networks"],
        responses={200: NetworkMembershipSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def membership_requests(self, request, pk=None):
        """Get pending membership requests for a network (admin only)."""
        try:
            network = self.get_object()

            # Check if user is admin
            if not (
                network.created_by == request.user
                or request.user in network.admins.all()
            ):
                raise PermissionDenied(
                    "Only network admins can view membership requests"
                )

            pending_requests = (
                NetworkMembership.objects.filter(
                    network=network,
                    status=NetworkMembership.MembershipStatus.PENDING,
                )
                .select_related("user")
                .order_by("-joined_at")
            )

            page = self.paginate_queryset(pending_requests)
            if page is not None:
                serializer = NetworkMembershipSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = NetworkMembershipSerializer(pending_requests, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error getting membership requests: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get membership requests"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Networks"],
        parameters=[
            OpenApiParameter(
                "user_id", OpenApiTypes.INT, description="User ID to approve"
            ),
        ],
        responses={200: NetworkMembershipSerializer},
    )
    @action(detail=True, methods=["post"])
    def approve_membership(self, request, pk=None):
        """Approve a membership request (admin only)."""
        try:
            network = self.get_object()
            user_id = request.data.get("user_id")

            if not user_id:
                return Response(
                    {"error": "user_id is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            membership = NetworkMembership.objects.filter(
                network=network,
                user_id=user_id,
                status=NetworkMembership.MembershipStatus.PENDING,
            ).first()

            if not membership:
                return Response(
                    {"error": "Membership request not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            membership.status = NetworkMembership.MembershipStatus.ACTIVE
            membership.save()

            # Update member count
            network.member_count = NetworkMembership.objects.filter(
                network=network,
                status=NetworkMembership.MembershipStatus.ACTIVE,
            ).count()
            network.save()

            # Notify user
            Notification.objects.create(
                recipient=membership.user,
                sender=request.user,
                notification_type=Notification.NotificationType.NETWORK_INVITATION,
                title=f"Welcome to {network.name}",
                message=f"Your request to join {network.name} has been approved.",
                data={"network_id": str(network.id)},
            )

            return Response(NetworkMembershipSerializer(membership).data)

        except Exception as e:
            logger.error(f"Error approving membership: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to approve membership"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Networks"],
        parameters=[
            OpenApiParameter(
                "user_id", OpenApiTypes.INT, description="User ID to reject"
            ),
        ],
        responses={204: None},
    )
    @action(detail=True, methods=["delete"])
    def reject_membership(self, request, pk=None):
        """Reject a membership request (admin only)."""
        try:
            network = self.get_object()
            user_id = request.data.get("user_id")

            if not user_id:
                return Response(
                    {"error": "user_id is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            membership = NetworkMembership.objects.filter(
                network=network,
                user_id=user_id,
                status=NetworkMembership.MembershipStatus.PENDING,
            ).first()

            if not membership:
                return Response(
                    {"error": "Membership request not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            membership.delete()

            # Notify user
            Notification.objects.create(
                recipient=membership.user,
                sender=request.user,
                notification_type=Notification.NotificationType.NETWORK_INVITATION,
                title="Network request declined",
                message=f"Your request to join {network.name} was declined.",
                data={"network_id": str(network.id)},
            )

            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception as e:
            logger.error(f"Error rejecting membership: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to reject membership"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Networks"],
        parameters=[
            OpenApiParameter(
                "user_id", OpenApiTypes.INT, description="User ID to invite"
            ),
        ],
        responses={201: NetworkMembershipSerializer},
    )
    @action(detail=True, methods=["post"])
    def invite_user(self, request, pk=None):
        """Invite a user to join the network."""
        try:
            network = self.get_object()
            user_id = request.data.get("user_id")

            if not user_id:
                return Response(
                    {"error": "user_id is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                invited_user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response(
                    {"error": "User not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Check if user is already a member
            existing_membership = NetworkMembership.objects.filter(
                user=invited_user,
                network=network,
            ).first()

            if existing_membership:
                return Response(
                    {"error": "User is already a member or has a pending request"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Create membership with pending status
            membership = NetworkMembership.objects.create(
                user=invited_user,
                network=network,
                status=NetworkMembership.MembershipStatus.PENDING,
            )

            # Notify invited user
            Notification.objects.create(
                recipient=invited_user,
                sender=request.user,
                notification_type=Notification.NotificationType.NETWORK_INVITATION,
                title=f"Invitation to join {network.name}",
                message=f"{request.user.get_full_name()} invited you to join {network.name}.",
                data={
                    "network_id": str(network.id),
                    "membership_id": str(membership.id),
                },
            )

            return Response(
                NetworkMembershipSerializer(membership).data,
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.error(f"Error inviting user to network: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to invite user"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Networks"],
        parameters=[
            OpenApiParameter(
                "user_id", OpenApiTypes.INT, description="User ID to remove"
            ),
        ],
        responses={204: None},
    )
    @action(detail=True, methods=["delete"])
    def remove_member(self, request, pk=None):
        """Remove a member from the network (admin only)."""
        try:
            network = self.get_object()
            user_id = request.data.get("user_id")

            if not user_id:
                return Response(
                    {"error": "user_id is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                user_to_remove = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response(
                    {"error": "User not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Cannot remove network creator
            if network.created_by == user_to_remove:
                return Response(
                    {"error": "Cannot remove network creator"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            membership = NetworkMembership.objects.filter(
                network=network,
                user=user_to_remove,
                status=NetworkMembership.MembershipStatus.ACTIVE,
            ).first()

            if not membership:
                return Response(
                    {"error": "User is not a member of this network"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            membership.delete()

            # Remove from admins if applicable
            if user_to_remove in network.admins.all():
                network.admins.remove(user_to_remove)

            # Update member count
            network.member_count = NetworkMembership.objects.filter(
                network=network,
                status=NetworkMembership.MembershipStatus.ACTIVE,
            ).count()
            network.save()

            # Notify removed user
            Notification.objects.create(
                recipient=user_to_remove,
                sender=request.user,
                notification_type=Notification.NotificationType.NETWORK_INVITATION,
                title=f"Removed from {network.name}",
                message=f"You have been removed from {network.name}.",
                data={"network_id": str(network.id)},
            )

            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception as e:
            logger.error(f"Error removing member: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to remove member"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Networks"],
        responses={200: {"statistics": "dict"}},
    )
    @action(detail=True, methods=["get"])
    def statistics(self, request, pk=None):
        """Get network statistics (admin only)."""
        try:
            network = self.get_object()

            # Check if user is admin
            if not (
                network.created_by == request.user
                or request.user in network.admins.all()
            ):
                raise PermissionDenied("Only network admins can view statistics")

            memberships = NetworkMembership.objects.filter(network=network)

            stats = {
                "total_members": memberships.filter(
                    status=NetworkMembership.MembershipStatus.ACTIVE
                ).count(),
                "pending_requests": memberships.filter(
                    status=NetworkMembership.MembershipStatus.PENDING
                ).count(),
                "inactive_members": memberships.filter(
                    status=NetworkMembership.MembershipStatus.INACTIVE
                ).count(),
                "banned_members": memberships.filter(
                    status=NetworkMembership.MembershipStatus.BANNED
                ).count(),
                "member_growth": [],
                "top_contributors": [],
                "member_locations": {},
                "member_companies": {},
            }

            # Get member growth over time (last 12 months)
            # This would require more complex aggregation
            # For now, return basic stats

            return Response({"statistics": stats})

        except Exception as e:
            logger.error(f"Error getting network statistics: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get network statistics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Networks"],
        parameters=[
            OpenApiParameter(
                "industry", OpenApiTypes.STR, description="Industry filter"
            ),
            OpenApiParameter(
                "location", OpenApiTypes.STR, description="Location filter"
            ),
        ],
        responses={200: NetworkSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def discover(self, request):
        """Discover networks based on user's profile and interests."""
        try:
            queryset = self.get_queryset().filter(is_public=True)

            # Filter by user's current company industry
            if request.user.current_company:
                # This is a simplified version - in reality you'd want a more sophisticated
                # industry matching system
                company_networks = queryset.filter(
                    name__icontains=request.user.current_company
                )
                if company_networks.exists():
                    queryset = company_networks

            # Filter by location
            if request.user.location:
                location_networks = queryset.filter(
                    location__icontains=request.user.location
                )
                if location_networks.exists():
                    queryset = location_networks

            # Get networks with most members (popular)
            queryset = queryset.order_by("-member_count")[:20]

            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error discovering networks: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to discover networks"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
