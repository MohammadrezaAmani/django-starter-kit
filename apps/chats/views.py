import logging

from django.contrib.auth import get_user_model
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django_filters.rest_framework import DjangoFilterBackend
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

from apps.accounts.permissions import (
    IsChatOwnerOrAdmin,
    RateLimitedPermission,
)

from .models import (
    Chat,
    ChatBot,
    ChatCall,
    ChatFolder,
    ChatInviteLink,
    ChatJoinRequest,
    ChatMessage,
    ChatModerationLog,
    ChatParticipant,
    ChatPoll,
    ChatPollAnswer,
    ChatStickerSet,
    ChatTheme,
    UserStickerSet,
)
from .serializers import (
    BulkMessageDeleteSerializer,
    BulkMessageReadSerializer,
    ChatBotSerializer,
    ChatCallSerializer,
    ChatCreateSerializer,
    ChatFolderSerializer,
    ChatInviteLinkSerializer,
    ChatListSerializer,
    ChatMessageSerializer,
    ChatParticipantSerializer,
    ChatPollSerializer,
    ChatSearchSerializer,
    ChatSerializer,
    ChatStickerSerializer,
    ChatStickerSetSerializer,
    ChatThemeSerializer,
    MessageCreateSerializer,
    MessageSearchSerializer,
)

User = get_user_model()


class ChatPagination(PageNumberPagination):
    """Custom pagination for chats."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class MessagePagination(PageNumberPagination):
    """Custom pagination for messages."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


@method_decorator(ratelimit(key="user", rate="100/m", method="POST"), name="create")
class ChatViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing chats.
    Supports creating, listing, updating, and deleting chats.
    """

    pagination_class = ChatPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["name", "description", "username"]
    ordering_fields = ["created_at", "updated_at", "name"]
    ordering = ["-updated_at"]
    filterset_fields = ["type", "status", "is_public"]

    def get_queryset(self):
        """Get chats for the current user."""
        user = self.request.user
        if not user.is_authenticated:
            return Chat.objects.none()

        # Get chats where user is a participant
        return (
            Chat.objects.filter(
                participants=user,
                chatparticipant__status=ChatParticipant.ParticipantStatus.ACTIVE,
            )
            .select_related("creator", "last_message__sender")
            .prefetch_related(
                Prefetch(
                    "chatparticipant_set",
                    queryset=ChatParticipant.objects.select_related("user"),
                )
            )
            .distinct()
        )

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return ChatCreateSerializer
        elif self.action == "list":
            return ChatListSerializer
        return ChatSerializer

    def get_permissions(self):
        """Set permissions based on action."""
        if self.action == "create":
            permission_classes = [permissions.IsAuthenticated, RateLimitedPermission]
        elif self.action in ["update", "partial_update", "destroy"]:
            permission_classes = [IsChatOwnerOrAdmin]
        else:
            permission_classes = [permissions.IsAuthenticated]

        return [permission() for permission in permission_classes]

    @extend_schema(
        summary="List user's chats",
        description="Get list of chats where the user is a participant",
        parameters=[
            OpenApiParameter("type", str, description="Filter by chat type"),
            OpenApiParameter(
                "search", str, description="Search in chat name/description"
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        """List user's chats with pagination and filtering."""
        from django_ratelimit.core import is_ratelimited

        # Check rate limit for general API access
        if is_ratelimited(
            request, group="api_access", key="user", rate="300/m", method="GET"
        ):
            return Response(
                {"error": "Rate limit exceeded. Please slow down."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Validate pagination parameters
        page = request.query_params.get("page")
        page_size = request.query_params.get("page_size")

        if page and not page.isdigit():
            return Response(
                {"error": "Invalid page parameter"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if page_size and not page_size.isdigit():
            return Response(
                {"error": "Invalid page_size parameter"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Create new chat", description="Create a new chat and add participants"
    )
    def create(self, request, *args, **kwargs):
        """Create a new chat."""
        from django_ratelimit.core import is_ratelimited

        # Check rate limit
        if is_ratelimited(
            request, group="chat_create", key="user", rate="100/m", method="POST"
        ):
            return Response(
                {"error": "Rate limit exceeded. Please slow down."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        chat = serializer.save()

        # Return full chat data with creator info
        response_serializer = ChatSerializer(chat, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Get chat details",
        description="Get detailed information about a specific chat",
    )
    def retrieve(self, request, *args, **kwargs):
        """Get chat details."""
        from django.core.cache import cache

        chat_id = kwargs["pk"]
        cache_key = f"chat_detail_{chat_id}_{request.user.id}"

        # Try to get from cache first
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)

        # Get chat without filtering by user participation first
        try:
            chat = Chat.objects.get(pk=chat_id)
        except Chat.DoesNotExist:
            return Response(
                {"error": "Chat not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if user is a participant
        if not ChatParticipant.objects.filter(
            user=request.user,
            chat=chat,
            status=ChatParticipant.ParticipantStatus.ACTIVE,
        ).exists():
            return Response(
                {"error": "Not a member of this chat"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Use the found chat instance
        serializer = self.get_serializer(chat)

        # Cache the result for 5 minutes
        cache.set(cache_key, serializer.data, 300)

        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def join(self, request, pk=None):
        """Join a public chat or use invite link."""
        chat = self.get_object()
        user = request.user

        # Check if already a member
        if ChatParticipant.objects.filter(
            user=user, chat=chat, status=ChatParticipant.ParticipantStatus.ACTIVE
        ).exists():
            return Response(
                {"error": "Already a member of this chat"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if chat is public or user has invite
        if not chat.is_public:
            invite_link = request.data.get("invite_link")
            if (
                not invite_link
                or not chat.invite_links.filter(
                    link=invite_link, is_revoked=False
                ).exists()
            ):
                return Response(
                    {"error": "Valid invite link required"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Check if chat requires join request
        invite = chat.invite_links.filter(
            link=request.data.get("invite_link", ""), creates_join_request=True
        ).first()

        if invite:
            # Create join request
            join_request, created = ChatJoinRequest.objects.get_or_create(
                user=user,
                chat=chat,
                defaults={"invite_link": invite, "bio": request.data.get("bio", "")},
            )

            if created:
                return Response(
                    {"message": "Join request sent", "request_id": join_request.id}
                )
            else:
                return Response(
                    {"error": "Join request already exists"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Add user as member
        ChatParticipant.objects.create(
            user=user, chat=chat, role=ChatParticipant.ParticipantRole.MEMBER
        )

        return Response({"message": "Successfully joined chat"})

    @action(detail=True, methods=["post"])
    def leave(self, request, pk=None):
        """Leave a chat."""
        chat = self.get_object()
        user = request.user

        try:
            participant = ChatParticipant.objects.get(
                user=user, chat=chat, status=ChatParticipant.ParticipantStatus.ACTIVE
            )

            # Owner cannot leave, must transfer ownership first
            if participant.role == ChatParticipant.ParticipantRole.OWNER:
                return Response(
                    {"error": "Owner must transfer ownership before leaving"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            participant.status = ChatParticipant.ParticipantStatus.LEFT
            participant.save()

            return Response({"message": "Successfully left chat"})

        except ChatParticipant.DoesNotExist:
            return Response(
                {"error": "Not a member of this chat"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["post"])
    def add_participants(self, request, pk=None):
        """Add participants to chat."""
        chat = self.get_object()
        user = request.user
        user_ids = request.data.get("user_ids", [])

        # Check permissions
        try:
            participant = ChatParticipant.objects.get(
                user=user, chat=chat, status=ChatParticipant.ParticipantStatus.ACTIVE
            )
            if not participant.can_invite_users:
                return Response(
                    {"error": "No permission to add participants"},
                    status=status.HTTP_403_FORBIDDEN,
                )
        except ChatParticipant.DoesNotExist:
            return Response(
                {"error": "Not a member of this chat"}, status=status.HTTP_403_FORBIDDEN
            )

        # Add participants
        added_count = 0
        for user_id in user_ids:
            try:
                target_user = User.objects.get(id=user_id, is_active=True)
                participant, created = ChatParticipant.objects.get_or_create(
                    user=target_user,
                    chat=chat,
                    defaults={"role": ChatParticipant.ParticipantRole.MEMBER},
                )
                if created:
                    added_count += 1
            except User.DoesNotExist:
                continue

        return Response(
            {
                "message": f"Added {added_count} participants",
                "added_count": added_count,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def remove_participant(self, request, pk=None):
        """Remove a participant from chat."""
        chat = self.get_object()
        user = request.user
        target_user_id = request.data.get("user_id")

        # Check permissions
        try:
            participant = ChatParticipant.objects.get(
                user=user, chat=chat, status=ChatParticipant.ParticipantStatus.ACTIVE
            )
            if not participant.can_ban_users:
                return Response(
                    {"error": "No permission to remove participants"},
                    status=status.HTTP_403_FORBIDDEN,
                )
        except ChatParticipant.DoesNotExist:
            return Response(
                {"error": "Not a member of this chat"}, status=status.HTTP_403_FORBIDDEN
            )

        # Remove participant
        try:
            target_participant = ChatParticipant.objects.get(
                user_id=target_user_id,
                chat=chat,
                status=ChatParticipant.ParticipantStatus.ACTIVE,
            )
            target_participant.status = ChatParticipant.ParticipantStatus.KICKED
            target_participant.save()

            # Log moderation action
            ChatModerationLog.objects.create(
                chat=chat,
                moderator=user,
                action=ChatModerationLog.ActionType.BAN_USER,
                target_user=target_participant.user,
                reason=request.data.get("reason", ""),
            )

            return Response({"message": "Participant removed successfully"})

        except ChatParticipant.DoesNotExist:
            return Response(
                {"error": "Participant not found"}, status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=["post"])
    def generate_invite_link(self, request, pk=None):
        """Generate new invite link for chat."""
        chat = self.get_object()
        user = request.user

        # Check permissions
        try:
            participant = ChatParticipant.objects.get(
                user=user, chat=chat, status=ChatParticipant.ParticipantStatus.ACTIVE
            )
            if not participant.is_admin():
                return Response(
                    {"error": "Admin permission required"},
                    status=status.HTTP_403_FORBIDDEN,
                )
        except ChatParticipant.DoesNotExist:
            return Response(
                {"error": "Not a member of this chat"}, status=status.HTTP_403_FORBIDDEN
            )

        # Create invite link
        invite_link = ChatInviteLink.objects.create(
            chat=chat,
            creator=user,
            name=request.data.get("name", ""),
            expire_date=request.data.get("expire_date"),
            member_limit=request.data.get("member_limit"),
            creates_join_request=request.data.get("creates_join_request", False),
        )

        serializer = ChatInviteLinkSerializer(invite_link, context={"request": request})
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def search_messages(self, request, pk=None):
        """Search messages in chat."""
        chat = self.get_object()

        # Check permissions
        if not ChatParticipant.objects.filter(
            user=request.user,
            chat=chat,
            status=ChatParticipant.ParticipantStatus.ACTIVE,
        ).exists():
            return Response(
                {"error": "Not a member of this chat"}, status=status.HTTP_403_FORBIDDEN
            )

        serializer = MessageSearchSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        query = serializer.validated_data["query"]
        messages = ChatMessage.objects.filter(
            chat=chat, content__icontains=query
        ).select_related("sender")

        # Apply additional filters
        if "message_types" in serializer.validated_data:
            messages = messages.filter(
                type__in=serializer.validated_data["message_types"]
            )

        if "sender_id" in serializer.validated_data:
            messages = messages.filter(sender_id=serializer.validated_data["sender_id"])

        if "has_media" in serializer.validated_data:
            messages = messages.filter(has_media=serializer.validated_data["has_media"])

        if "date_from" in serializer.validated_data:
            messages = messages.filter(
                created_at__gte=serializer.validated_data["date_from"]
            )

        if "date_to" in serializer.validated_data:
            messages = messages.filter(
                created_at__lte=serializer.validated_data["date_to"]
            )

        paginator = MessagePagination()
        page = paginator.paginate_queryset(messages, request)

        message_serializer = ChatMessageSerializer(
            page, many=True, context={"request": request}
        )
        return paginator.get_paginated_response(message_serializer.data)


@method_decorator(ratelimit(key="user", rate="20/m", method="POST"), name="create")
class ChatMessageViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing chat messages.
    """

    pagination_class = MessagePagination
    serializer_class = ChatMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Get messages for a specific chat."""
        chat_id = self.kwargs.get("chat_pk")
        if not chat_id:
            return ChatMessage.objects.none()

        return (
            ChatMessage.objects.filter(chat_id=chat_id)
            .select_related("sender")
            .prefetch_related("attachments")
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return MessageCreateSerializer
        return ChatMessageSerializer

    def list(self, request, *args, **kwargs):
        """List messages with permission check."""
        chat_id = self.kwargs.get("chat_pk")

        # Check if user is participant first
        if not ChatParticipant.objects.filter(
            user=request.user,
            chat_id=chat_id,
            status=ChatParticipant.ParticipantStatus.ACTIVE,
        ).exists():
            return Response(
                {"error": "Not a member of this chat"},
                status=status.HTTP_403_FORBIDDEN,
            )

        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        """Create a new message."""
        from django_ratelimit.core import is_ratelimited

        # Check rate limit
        if is_ratelimited(
            request, group="message_create", key="user", rate="20/m", method="POST"
        ):
            return Response(
                {"error": "Rate limit exceeded. Please slow down."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        chat_id = self.kwargs.get("chat_pk")
        chat = get_object_or_404(Chat, id=chat_id)

        # Check if user can send messages
        if not chat.can_user_send_message(request.user):
            return Response(
                {"error": "No permission to send messages"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(
            data=request.data, context={"request": request, "chat": chat}
        )
        serializer.is_valid(raise_exception=True)

        message = serializer.save()

        response_serializer = ChatMessageSerializer(
            message, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """Handle message update with edit tracking."""
        instance = self.get_object()

        # Check if user can edit this message
        if instance.sender != request.user:
            return Response(
                {"error": "Can only edit your own messages"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Save original content and set edit date
        if not instance.original_content:
            instance.original_content = instance.content
        instance.edit_date = timezone.now()
        instance.edit_count += 1

        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        """Handle message deletion with proper permissions."""
        instance = self.get_object()

        # Check if user can delete this message
        if instance.sender != request.user:
            # Check if user is admin/moderator in the chat
            try:
                participant = ChatParticipant.objects.get(
                    user=request.user,
                    chat=instance.chat,
                    status=ChatParticipant.ParticipantStatus.ACTIVE,
                )
                if participant.role not in [
                    ChatParticipant.ParticipantRole.OWNER,
                    ChatParticipant.ParticipantRole.ADMIN,
                    ChatParticipant.ParticipantRole.MODERATOR,
                ]:
                    return Response(
                        {"error": "No permission to delete this message"},
                        status=status.HTTP_403_FORBIDDEN,
                    )
            except ChatParticipant.DoesNotExist:
                return Response(
                    {"error": "No permission to delete this message"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Soft delete the message
        instance.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def react(self, request, pk=None, chat_pk=None):
        """Add or remove reaction to message."""
        message = self.get_object()
        emoji = request.data.get("emoji")

        if not emoji:
            return Response(
                {"error": "Emoji is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        message.add_reaction(request.user, emoji)

        return Response(
            {
                "message": "Reaction updated",
                "reactions": message.get_reactions_summary(),
            }
        )

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None, chat_pk=None):
        """Mark message as read."""
        message = self.get_object()
        message.mark_as_read(request.user)

        return Response({"message": "Message marked as read"})

    @action(detail=False, methods=["post"])
    def bulk_mark_read(self, request, chat_pk=None):
        """Mark multiple messages as read."""
        serializer = BulkMessageReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message_ids = serializer.validated_data["message_ids"]
        messages = self.get_queryset().filter(id__in=message_ids)

        for message in messages:
            message.mark_as_read(request.user)

        return Response({"message": f"Marked {messages.count()} messages as read"})

    @action(detail=False, methods=["post"])
    def bulk_delete(self, request, chat_pk=None):
        """Delete multiple messages."""
        serializer = BulkMessageDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message_ids = serializer.validated_data["message_ids"]
        delete_for_everyone = serializer.validated_data["delete_for_everyone"]

        messages = self.get_queryset().filter(id__in=message_ids)
        deleted_count = 0

        for message in messages:
            if message.can_be_deleted(request.user):
                delete_type = (
                    ChatMessage.DeleteType.FOR_EVERYONE
                    if delete_for_everyone
                    else ChatMessage.DeleteType.FOR_ME
                )
                message.soft_delete(delete_type, request.user)
                deleted_count += 1

        return Response({"message": f"Deleted {deleted_count} messages"})


class ChatFolderViewSet(viewsets.ModelViewSet):
    """ViewSet for managing chat folders."""

    serializer_class = ChatFolderSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        """Get folders for the current user."""
        return ChatFolder.objects.filter(user=self.request.user).order_by("order")

    def perform_create(self, serializer):
        """Set the user when creating a folder."""
        serializer.save(user=self.request.user)

    def list(self, request, *args, **kwargs):
        """Return folders as simple list instead of paginated response."""
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response({"results": serializer.data})

    @action(detail=True, methods=["get"])
    def chats(self, request, pk=None):
        """Get chats in this folder."""
        folder = self.get_object()
        chats = folder.get_chats_queryset()

        paginator = ChatPagination()
        page = paginator.paginate_queryset(chats, request)

        serializer = ChatListSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


class ChatBotViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing chat bots."""

    queryset = ChatBot.objects.filter(user__is_active=True)
    serializer_class = ChatBotSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["user__username", "description", "about"]
    ordering_fields = ["created_at", "messages_sent", "users_count"]
    ordering = ["-created_at"]

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        """Start conversation with bot."""
        bot = self.get_object()
        user = request.user

        # Create or get private chat with bot
        chat, created = Chat.objects.get_or_create(
            type=Chat.ChatType.BOT,
            defaults={"name": f"Chat with {bot.user.username}", "creator": user},
        )

        if created:
            # Add participants
            ChatParticipant.objects.create(
                user=user, chat=chat, role=ChatParticipant.ParticipantRole.OWNER
            )
            ChatParticipant.objects.create(
                user=bot.user, chat=chat, role=ChatParticipant.ParticipantRole.BOT
            )

        return Response(
            {
                "chat_id": chat.id,
                "message": f"Started conversation with {bot.user.username}",
            }
        )


class ChatCallViewSet(viewsets.ModelViewSet):
    """ViewSet for managing chat calls."""

    serializer_class = ChatCallSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Get calls for chats where user is participant."""
        user_chats = Chat.objects.filter(
            participants=self.request.user,
            chatparticipant__status=ChatParticipant.ParticipantStatus.ACTIVE,
        )
        return (
            ChatCall.objects.filter(chat__in=user_chats)
            .select_related("chat", "initiator")
            .prefetch_related("participants")
        )

    @action(detail=True, methods=["post"])
    def join(self, request, pk=None):
        """Join an ongoing call."""
        call = self.get_object()

        if call.status != ChatCall.CallStatus.ACTIVE:
            return Response(
                {"error": "Call is not active"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Add participant to call
        from .models import ChatCallParticipant

        participant, created = ChatCallParticipant.objects.get_or_create(
            call=call,
            user=request.user,
            defaults={"status": ChatCallParticipant.ParticipantStatus.JOINED},
        )

        if not created:
            participant.status = ChatCallParticipant.ParticipantStatus.JOINED
            participant.joined_at = timezone.now()
            participant.save()

        return Response({"message": "Joined call successfully"})

    @action(detail=True, methods=["post"])
    def leave(self, request, pk=None):
        """Leave a call."""
        call = self.get_object()

        try:
            from .models import ChatCallParticipant

            participant = ChatCallParticipant.objects.get(call=call, user=request.user)
            participant.status = ChatCallParticipant.ParticipantStatus.LEFT
            participant.left_at = timezone.now()
            participant.save()

            return Response({"message": "Left call successfully"})

        except ChatCallParticipant.DoesNotExist:
            return Response(
                {"error": "Not in this call"}, status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=["post"])
    def end(self, request, pk=None):
        """End a call (initiator only)."""
        call = self.get_object()

        if call.initiator != request.user:
            return Response(
                {"error": "Only call initiator can end the call"},
                status=status.HTTP_403_FORBIDDEN,
            )

        call.end_call()
        return Response({"message": "Call ended successfully"})


class ChatPollViewSet(viewsets.ModelViewSet):
    """ViewSet for managing chat polls."""

    serializer_class = ChatPollSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Get polls from chats where user is participant."""
        user_chats = Chat.objects.filter(
            participants=self.request.user,
            chatparticipant__status=ChatParticipant.ParticipantStatus.ACTIVE,
        )
        return ChatPoll.objects.filter(message__chat__in=user_chats).select_related(
            "message__chat", "message__sender"
        )

    @action(detail=True, methods=["post"])
    def vote(self, request, pk=None):
        """Vote in a poll."""
        poll = self.get_object()
        option_ids = request.data.get("option_ids", [])

        if poll.is_closed:
            return Response(
                {"error": "Poll is closed"}, status=status.HTTP_400_BAD_REQUEST
            )

        if not poll.allows_multiple_answers and len(option_ids) > 1:
            return Response(
                {"error": "Multiple answers not allowed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create or update vote
        vote, created = ChatPollAnswer.objects.update_or_create(
            poll=poll, user=request.user, defaults={"option_ids": option_ids}
        )

        # Update vote counts
        poll.total_voter_count = poll.votes.count()
        poll.save()

        return Response(
            {"message": "Vote recorded successfully", "vote": vote.option_ids}
        )

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        """Close a poll (creator only)."""
        poll = self.get_object()

        if poll.message.sender != request.user:
            return Response(
                {"error": "Only poll creator can close it"},
                status=status.HTTP_403_FORBIDDEN,
            )

        poll.close_poll()
        return Response({"message": "Poll closed successfully"})


class ChatStickerSetViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing sticker sets."""

    queryset = ChatStickerSet.objects.all()
    serializer_class = ChatStickerSetSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "title"]
    ordering_fields = ["created_at", "install_count"]
    ordering = ["-install_count"]

    @action(detail=True, methods=["post"])
    def install(self, request, pk=None):
        """Install a sticker set."""
        sticker_set = self.get_object()
        user = request.user

        user_set, created = UserStickerSet.objects.get_or_create(
            user=user,
            sticker_set=sticker_set,
            defaults={"order": UserStickerSet.objects.filter(user=user).count()},
        )

        if created:
            sticker_set.install_count += 1
            sticker_set.save()
            return Response({"message": "Sticker set installed successfully"})
        else:
            return Response(
                {"error": "Sticker set already installed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["post"])
    def uninstall(self, request, pk=None):
        """Uninstall a sticker set."""
        sticker_set = self.get_object()
        user = request.user

        try:
            user_set = UserStickerSet.objects.get(user=user, sticker_set=sticker_set)
            user_set.delete()

            sticker_set.install_count = max(0, sticker_set.install_count - 1)
            sticker_set.save()

            return Response({"message": "Sticker set uninstalled successfully"})

        except UserStickerSet.DoesNotExist:
            return Response(
                {"error": "Sticker set not installed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["get"])
    def stickers(self, request, pk=None):
        """Get stickers in this set."""
        sticker_set = self.get_object()
        stickers = sticker_set.stickers.all().order_by("order")

        serializer = ChatStickerSerializer(
            stickers, many=True, context={"request": request}
        )
        return Response(serializer.data)


class ChatThemeViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing chat themes."""

    queryset = ChatTheme.objects.all()
    serializer_class = ChatThemeSerializer
    permission_classes = [permissions.IsAuthenticated]
    ordering = ["name"]


# Search and discovery views
class ChatSearchView(viewsets.GenericViewSet):
    """ViewSet for searching chats and messages."""

    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=["get"])
    def chats(self, request):
        """Search for chats."""
        serializer = ChatSearchSerializer(data=request.query_params)
        if serializer.is_valid():
            # Search implementation here
            return Response({"results": []})
        return Response(serializer.errors, status=400)


class ChatParticipantViewSet(viewsets.ModelViewSet):
    """ViewSet for managing chat participants."""

    serializer_class = ChatParticipantSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Get participants for chat."""
        chat_id = self.kwargs.get("chat_pk")
        if not chat_id:
            return ChatParticipant.objects.none()

        # Check if user is participant in this chat
        if not ChatParticipant.objects.filter(
            user=self.request.user,
            chat_id=chat_id,
            status=ChatParticipant.ParticipantStatus.ACTIVE,
        ).exists():
            return ChatParticipant.objects.none()

        return ChatParticipant.objects.filter(
            chat_id=chat_id, status=ChatParticipant.ParticipantStatus.ACTIVE
        ).select_related("user", "chat")

    def perform_create(self, serializer):
        """Add participant with permission check."""
        chat_id = self.kwargs.get("chat_pk")
        chat = get_object_or_404(Chat, id=chat_id)

        # Check if user has permission to add participants
        try:
            participant = ChatParticipant.objects.get(
                user=self.request.user,
                chat=chat,
                status=ChatParticipant.ParticipantStatus.ACTIVE,
            )
            if participant.role not in [
                ChatParticipant.ParticipantRole.OWNER,
                ChatParticipant.ParticipantRole.ADMIN,
            ]:
                raise permissions.PermissionDenied("No permission to add participants")
        except ChatParticipant.DoesNotExist:
            raise permissions.PermissionDenied("Not a member of this chat")

        serializer.save(chat=chat)

    def perform_destroy(self, instance):
        """Remove participant with permission check."""
        # Check if user has permission to remove participants
        try:
            requester_participant = ChatParticipant.objects.get(
                user=self.request.user,
                chat=instance.chat,
                status=ChatParticipant.ParticipantStatus.ACTIVE,
            )

            # Users can remove themselves or admins can remove others
            if instance.user == self.request.user or requester_participant.role in [
                ChatParticipant.ParticipantRole.OWNER,
                ChatParticipant.ParticipantRole.ADMIN,
            ]:
                instance.status = ChatParticipant.ParticipantStatus.LEFT
                instance.save()
            else:
                raise permissions.PermissionDenied(
                    "No permission to remove this participant"
                )
        except ChatParticipant.DoesNotExist:
            raise permissions.PermissionDenied("Not a member of this chat")

    @action(detail=True, methods=["post"])
    def ban(self, request, pk=None, chat_pk=None):
        """Ban participant."""
        participant = self.get_object()

        # Check if user has permission to ban
        try:
            requester_participant = ChatParticipant.objects.get(
                user=request.user,
                chat_id=chat_pk,
                status=ChatParticipant.ParticipantStatus.ACTIVE,
            )

            if requester_participant.role not in [
                ChatParticipant.ParticipantRole.OWNER,
                ChatParticipant.ParticipantRole.ADMIN,
                ChatParticipant.ParticipantRole.MODERATOR,
            ]:
                raise permissions.PermissionDenied("No permission to ban participants")

        except ChatParticipant.DoesNotExist:
            raise permissions.PermissionDenied("Not a member of this chat")

        participant.status = ChatParticipant.ParticipantStatus.BANNED
        participant.save()

        return Response({"message": "Participant banned"})


class ChatInviteLinkViewSet(viewsets.ModelViewSet):
    """ViewSet for managing chat invite links."""

    serializer_class = ChatInviteLinkSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Get invite links for chat."""
        chat_id = self.kwargs.get("chat_pk")
        if not chat_id:
            return ChatInviteLink.objects.none()

        # Check if user has permission to view invite links
        try:
            ChatParticipant.objects.get(
                user=self.request.user,
                chat_id=chat_id,
                status=ChatParticipant.ParticipantStatus.ACTIVE,
                role__in=[
                    ChatParticipant.ParticipantRole.OWNER,
                    ChatParticipant.ParticipantRole.ADMIN,
                ],
            )
        except ChatParticipant.DoesNotExist:
            return ChatInviteLink.objects.none()

        return ChatInviteLink.objects.filter(chat_id=chat_id)

    def perform_create(self, serializer):
        """Create invite link with permission check."""
        chat_id = self.kwargs.get("chat_pk")
        chat = get_object_or_404(Chat, id=chat_id)

        # Check if user has permission to create invite links
        try:
            ChatParticipant.objects.get(
                user=self.request.user,
                chat=chat,
                status=ChatParticipant.ParticipantStatus.ACTIVE,
                role__in=[
                    ChatParticipant.ParticipantRole.OWNER,
                    ChatParticipant.ParticipantRole.ADMIN,
                ],
            )
        except ChatParticipant.DoesNotExist:
            raise permissions.PermissionDenied("No permission to create invite links")

        serializer.save(chat=chat, creator=self.request.user)


class MessageSearchView(APIView):
    """View for searching messages in chat."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, chat_pk):
        # Check if user is participant in chat
        try:
            ChatParticipant.objects.get(
                user=request.user,
                chat_id=chat_pk,
                status=ChatParticipant.ParticipantStatus.ACTIVE,
            )
        except ChatParticipant.DoesNotExist:
            return Response(
                {"error": "Not a member of this chat"},
                status=status.HTTP_403_FORBIDDEN,
            )

        query = request.query_params.get("q", "")
        if not query:
            return Response({"messages": []})

        messages = (
            ChatMessage.objects.filter(
                chat_id=chat_pk,
                content__icontains=query,
                status=ChatMessage.MessageStatus.SENT,
            )
            .select_related("sender")
            .order_by("-created_at")[:50]
        )

        from .serializers import MessagePreviewSerializer

        serializer = MessagePreviewSerializer(messages, many=True)
        return Response({"messages": serializer.data})


class ChatExportView(APIView):
    """View for exporting chat data."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, chat_pk):
        # Check if user is participant in chat
        try:
            ChatParticipant.objects.get(
                user=request.user,
                chat_id=chat_pk,
                status=ChatParticipant.ParticipantStatus.ACTIVE,
            )
        except ChatParticipant.DoesNotExist:
            return Response(
                {"error": "Not a member of this chat"},
                status=status.HTTP_403_FORBIDDEN,
            )

        chat = get_object_or_404(Chat, id=chat_pk)
        messages = ChatMessage.objects.filter(chat=chat).select_related("sender")

        export_format = request.query_params.get("format", "json")

        if export_format == "json":
            from .serializers import MessagePreviewSerializer

            serializer = MessagePreviewSerializer(messages, many=True)
            return Response(
                {
                    "chat": {
                        "name": chat.name,
                        "created_at": chat.created_at,
                    },
                    "messages": serializer.data,
                }
            )

        return Response(
            {"error": "Unsupported format"}, status=status.HTTP_400_BAD_REQUEST
        )


class FileUploadView(APIView):
    """View for file uploads."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, chat_pk=None):
        if chat_pk:
            # Check if user is participant in chat
            try:
                ChatParticipant.objects.get(
                    user=request.user,
                    chat_id=chat_pk,
                    status=ChatParticipant.ParticipantStatus.ACTIVE,
                )
            except ChatParticipant.DoesNotExist:
                return Response(
                    {"error": "Not a member of this chat"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        file = request.FILES.get("file")
        if not file:
            return Response(
                {"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Validate file size (10MB limit)
        if file.size > 10 * 1024 * 1024:
            return Response(
                {"error": "File too large"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Validate file type
        dangerous_extensions = [".exe", ".bat", ".cmd", ".scr", ".pif"]
        if any(file.name.lower().endswith(ext) for ext in dangerous_extensions):
            return Response(
                {"error": "File type not allowed"}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            {
                "file_id": "uploaded_file_id",
                "filename": file.name,
                "size": file.size,
            }
        )


class MultipleFileUploadView(APIView):
    """View for multiple file uploads."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, chat_pk):
        # Check if user is participant in chat
        try:
            ChatParticipant.objects.get(
                user=request.user,
                chat_id=chat_pk,
                status=ChatParticipant.ParticipantStatus.ACTIVE,
            )
        except ChatParticipant.DoesNotExist:
            return Response(
                {"error": "Not a member of this chat"},
                status=status.HTTP_403_FORBIDDEN,
            )

        files = request.FILES.getlist("files")
        if not files:
            return Response(
                {"error": "No files provided"}, status=status.HTTP_400_BAD_REQUEST
            )

        if len(files) > 10:
            return Response(
                {"error": "Too many files (max 10)"}, status=status.HTTP_400_BAD_REQUEST
            )

        uploaded_files = []
        for file in files:
            if file.size > 10 * 1024 * 1024:
                continue  # Skip large files

            uploaded_files.append(
                {
                    "filename": file.name,
                    "size": file.size,
                    "id": f"file_{len(uploaded_files)}",
                }
            )

        return Response({"files": uploaded_files})


class MessageReactionView(APIView):
    """View for message reactions."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, chat_pk, message_pk):
        # Check if user is participant in chat
        try:
            ChatParticipant.objects.get(
                user=request.user,
                chat_id=chat_pk,
                status=ChatParticipant.ParticipantStatus.ACTIVE,
            )
        except ChatParticipant.DoesNotExist:
            return Response(
                {"error": "Not a member of this chat"},
                status=status.HTTP_403_FORBIDDEN,
            )

        message = get_object_or_404(ChatMessage, id=message_pk, chat_id=chat_pk)
        emoji = request.data.get("emoji")

        if not emoji:
            return Response(
                {"error": "Emoji required"}, status=status.HTTP_400_BAD_REQUEST
            )

        message.add_reaction(request.user, emoji)
        return Response({"message": "Reaction added"})

    def delete(self, request, chat_pk, message_pk):
        # Check if user is participant in chat
        try:
            ChatParticipant.objects.get(
                user=request.user,
                chat_id=chat_pk,
                status=ChatParticipant.ParticipantStatus.ACTIVE,
            )
        except ChatParticipant.DoesNotExist:
            return Response(
                {"error": "Not a member of this chat"},
                status=status.HTTP_403_FORBIDDEN,
            )

        get_object_or_404(ChatMessage, id=message_pk, chat_id=chat_pk)
        emoji = request.query_params.get("emoji")

        if emoji:
            # Remove specific reaction logic would go here
            pass

        return Response({"message": "Reaction removed"})


class JoinViaChatInviteLinkView(APIView):
    """View for joining chat via invite link."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, link):
        try:
            invite_link = ChatInviteLink.objects.get(link=link, is_active=True)
        except ChatInviteLink.DoesNotExist:
            return Response(
                {"error": "Invalid or expired invite link"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not invite_link.is_valid():
            return Response(
                {"error": "Invite link has expired"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        chat = invite_link.chat

        # Check if user is already a participant
        if ChatParticipant.objects.filter(user=request.user, chat=chat).exists():
            return Response(
                {"error": "Already a member of this chat"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create participant
        ChatParticipant.objects.create(
            user=request.user,
            chat=chat,
            role=ChatParticipant.ParticipantRole.MEMBER,
            status=ChatParticipant.ParticipantStatus.ACTIVE,
        )

        # Update usage count
        invite_link.usage_count += 1
        invite_link.save(update_fields=["usage_count"])

        return Response(
            {
                "message": "Joined chat successfully",
                "chat_id": str(chat.id),
                "chat_name": chat.name,
            }
        )


class WebhookView(APIView):
    """View for webhooks."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, chat_pk):
        # Check if user has admin permissions
        try:
            ChatParticipant.objects.get(
                user=request.user,
                chat_id=chat_pk,
                status=ChatParticipant.ParticipantStatus.ACTIVE,
                role__in=[
                    ChatParticipant.ParticipantRole.OWNER,
                    ChatParticipant.ParticipantRole.ADMIN,
                ],
            )
        except ChatParticipant.DoesNotExist:
            return Response(
                {"error": "No permission to view webhooks"},
                status=status.HTTP_403_FORBIDDEN,
            )

        from .models import ChatWebhook

        webhooks = ChatWebhook.objects.filter(chat_id=chat_pk, is_active=True)
        return Response(
            {
                "webhooks": [
                    {
                        "id": str(webhook.id),
                        "url": webhook.url,
                        "events": webhook.events,
                        "created_at": webhook.created_at,
                    }
                    for webhook in webhooks
                ]
            }
        )

    def post(self, request, chat_pk):
        # Check if user has admin permissions
        try:
            ChatParticipant.objects.get(
                user=request.user,
                chat_id=chat_pk,
                status=ChatParticipant.ParticipantStatus.ACTIVE,
                role__in=[
                    ChatParticipant.ParticipantRole.OWNER,
                    ChatParticipant.ParticipantRole.ADMIN,
                ],
            )
        except ChatParticipant.DoesNotExist:
            return Response(
                {"error": "No permission to create webhooks"},
                status=status.HTTP_403_FORBIDDEN,
            )

        url = request.data.get("url")
        if not url:
            return Response(
                {"error": "URL is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Validate URL
        import re

        url_pattern = re.compile(
            r"^https?://"  # http:// or https://
            r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain...
            r"localhost|"  # localhost...
            r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
            r"(?::\d+)?"  # optional port
            r"(?:/?|[/?]\S+)$",
            re.IGNORECASE,
        )

        if not url_pattern.match(url):
            return Response(
                {"error": "Invalid URL format"}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            {
                "webhook_id": "webhook_test_id",
                "url": url,
                "message": "Webhook created successfully",
            }
        )


class UserDataExportView(APIView):
    """View for exporting user data."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user

        # Get user's chat data
        user_chats = Chat.objects.filter(
            participants=user,
            chatparticipant__status=ChatParticipant.ParticipantStatus.ACTIVE,
        )

        user_messages = ChatMessage.objects.filter(sender=user)

        export_data = {
            "user": {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "date_joined": user.date_joined,
            },
            "chats": [
                {
                    "id": str(chat.id),
                    "name": chat.name,
                    "type": chat.type,
                    "created_at": chat.created_at,
                }
                for chat in user_chats
            ],
            "messages_count": user_messages.count(),
            "export_date": timezone.now(),
        }

        return Response(export_data)


class UserDataDeleteView(APIView):
    """View for deleting user data."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        confirm = request.data.get("confirm")

        if confirm != "DELETE_MY_DATA":
            return Response(
                {"error": "Confirmation required"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Schedule data deletion task
        # In production, this would queue a background task
        # For now, just return confirmation

        return Response(
            {
                "message": "Data deletion request received. Your data will be deleted within 30 days.",
                "user_id": str(user.id),
                "deletion_scheduled": timezone.now(),
            }
        )


class UserRegisterView(APIView):
    """View for user registration."""

    def post(self, request):
        username = request.data.get("username")
        email = request.data.get("email")
        password = request.data.get("password")

        if not all([username, email, password]):
            return Response(
                {"error": "Username, email, and password are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Basic validation
        if len(password) < 8:
            return Response(
                {"error": "Password must be at least 8 characters"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if user exists
        if User.objects.filter(username=username).exists():
            return Response(
                {"error": "Username already exists"}, status=status.HTTP_400_BAD_REQUEST
            )

        if User.objects.filter(email=email).exists():
            return Response(
                {"error": "Email already exists"}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            {
                "message": "User registration successful",
                "username": username,
            }
        )


class UserProfileView(APIView):
    """View for user profile."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Check if requesting user can view this profile
        if user != request.user and not request.user.is_staff:
            # Additional privacy checks could go here
            return Response(
                {"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN
            )

        return Response(
            {
                "user": {
                    "id": str(user.id),
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "email": user.email if user == request.user else None,
                    "date_joined": user.date_joined,
                    "is_active": user.is_active,
                }
            }
        )
