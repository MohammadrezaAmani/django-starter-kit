import hashlib
import html
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import (
    Chat,
    ChatAttachment,
    ChatBot,
    ChatCall,
    ChatCallParticipant,
    ChatFolder,
    ChatInviteLink,
    ChatJoinRequest,
    ChatMessage,
    ChatModerationLog,
    ChatParticipant,
    ChatPoll,
    ChatPollAnswer,
    ChatSticker,
    ChatStickerSet,
    ChatTheme,
    UserStickerSet,
)

User = get_user_model()


class UserBasicSerializer(serializers.ModelSerializer):
    """
    Optimized basic user serializer for chat contexts.
    Includes caching and minimal fields for performance.
    """

    full_name = serializers.CharField(source="get_full_name", read_only=True)
    avatar = serializers.SerializerMethodField()
    is_online = serializers.SerializerMethodField()
    last_seen = serializers.DateTimeField(source="last_activity", read_only=True)
    status_emoji = serializers.CharField(source="profile.status_emoji", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "avatar",
            "is_online",
            "last_seen",
            "status_emoji",
        ]
        read_only_fields = ["id", "username"]

    def get_avatar(self, obj):
        """Get avatar URL with fallback and optimization."""
        if hasattr(obj, "profile") and obj.profile.profile_picture:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.profile.profile_picture.url)
            return obj.profile.profile_picture.url
        return None

    def get_is_online(self, obj):
        """Check if user is online with caching."""
        cache_key = f"user_online_{obj.id}"
        is_online = cache.get(cache_key)

        if is_online is None:
            if not obj.last_activity:
                is_online = False
            else:
                is_online = (timezone.now() - obj.last_activity).total_seconds() < 300
            cache.set(cache_key, is_online, 60)  # Cache for 1 minute

        return is_online


class ChatAttachmentSerializer(serializers.ModelSerializer):
    """
    Comprehensive attachment serializer with security validations.
    """

    file_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    file_size_display = serializers.SerializerMethodField()
    is_safe = serializers.SerializerMethodField()
    download_count = serializers.IntegerField(default=0, read_only=True)

    class Meta:
        model = ChatAttachment
        fields = [
            "id",
            "type",
            "file",
            "file_url",
            "thumbnail",
            "thumbnail_url",
            "file_name",
            "file_size",
            "file_size_display",
            "mime_type",
            "width",
            "height",
            "duration",
            "caption",
            "title",
            "performer",
            "is_encrypted",
            "is_safe",
            "download_count",
            "checksum",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "file_size",
            "checksum",
            "created_at",
            "download_count",
        ]

    def get_file_url(self, obj):
        """Get secure file URL with access control."""
        if obj.file:
            request = self.context.get("request")
            if request and request.user.is_authenticated:
                # Check if user has access to this file
                if self._has_file_access(obj, request.user):
                    if request:
                        return request.build_absolute_uri(obj.file.url)
                    return obj.file.url
        return None

    def get_thumbnail_url(self, obj):
        """Get thumbnail URL."""
        if obj.thumbnail:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.thumbnail.url)
            return obj.thumbnail.url
        return None

    def get_file_size_display(self, obj):
        """Human readable file size."""
        if not obj.file_size:
            return "0 B"

        size = obj.file_size
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def get_is_safe(self, obj):
        """Check if file is safe (basic security check)."""
        dangerous_extensions = [".exe", ".scr", ".bat", ".cmd", ".com", ".pif"]
        if obj.file_name:
            return not any(
                obj.file_name.lower().endswith(ext) for ext in dangerous_extensions
            )
        return True

    def _has_file_access(self, attachment, user):
        """Check if user has access to this attachment."""
        try:
            message = attachment.message
            chat = message.chat
            participant = chat.chatparticipant_set.get(user=user)
            return participant.status == ChatParticipant.ParticipantStatus.ACTIVE
        except (ChatParticipant.DoesNotExist, AttributeError):
            return False

    def validate_file(self, value):
        """Validate uploaded file."""
        if value:
            # Size limit (50MB)
            if value.size > 50 * 1024 * 1024:
                raise serializers.ValidationError("File size cannot exceed 50MB")

            # Content type validation
            content_type = getattr(value, "content_type", "")
            if not content_type:
                raise serializers.ValidationError("File content type is required")

        return value


class ChatMessageSerializer(serializers.ModelSerializer):
    """
    Comprehensive message serializer with performance optimizations.
    """

    sender = UserBasicSerializer(read_only=True)
    attachments = ChatAttachmentSerializer(many=True, read_only=True)
    reply_to = serializers.SerializerMethodField()
    forward_from = serializers.SerializerMethodField()
    reactions_summary = serializers.SerializerMethodField()
    is_edited = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    read_by = serializers.SerializerMethodField()
    mentions = serializers.JSONField(read_only=True)

    class Meta:
        model = ChatMessage
        fields = [
            "id",
            "sender",
            "type",
            "content",
            "status",
            "attachments",
            "reply_to",
            "forward_from",
            "has_media",
            "is_forwarded",
            "is_pinned",
            "is_silent",
            "is_scheduled",
            "scheduled_date",
            "reactions",
            "reactions_summary",
            "views_count",
            "forwards_count",
            "replies_count",
            "is_edited",
            "edit_date",
            "can_edit",
            "can_delete",
            "read_by",
            "mentions",
            "poll_data",
            "location_data",
            "contact_data",
            "call_data",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "sender",
            "status",
            "views_count",
            "forwards_count",
            "replies_count",
            "created_at",
            "updated_at",
        ]

    def get_reply_to(self, obj):
        """Get reply_to message with caching."""
        if obj.reply_to:
            cache_key = f"reply_to_{obj.reply_to.id}"
            reply_data = cache.get(cache_key)

            if reply_data is None:
                reply_data = {
                    "id": str(obj.reply_to.id),
                    "sender": (
                        {
                            "id": str(obj.reply_to.sender.id),
                            "username": obj.reply_to.sender.username,
                            "full_name": obj.reply_to.sender.get_full_name(),
                        }
                        if obj.reply_to.sender
                        else {"username": "System"}
                    ),
                    "content": obj.reply_to.content[:100]
                    + ("..." if len(obj.reply_to.content) > 100 else ""),
                    "type": obj.reply_to.type,
                    "has_media": obj.reply_to.has_media,
                    "created_at": obj.reply_to.created_at.isoformat(),
                }
                cache.set(cache_key, reply_data, 300)  # 5 minutes cache

            return reply_data
        return None

    def get_forward_from(self, obj):
        """Get forward_from message info."""
        if obj.forward_from:
            return {
                "id": str(obj.forward_from.id),
                "sender": (
                    {
                        "id": str(obj.forward_from.sender.id),
                        "username": obj.forward_from.sender.username,
                        "full_name": obj.forward_from.sender.get_full_name(),
                    }
                    if obj.forward_from.sender
                    else {"username": "System"}
                ),
                "chat": (
                    {
                        "id": str(obj.forward_from_chat.id),
                        "name": obj.forward_from_chat.name,
                        "type": obj.forward_from_chat.type,
                    }
                    if obj.forward_from_chat
                    else None
                ),
                "created_at": obj.forward_from.created_at.isoformat(),
            }
        return None

    def get_reactions_summary(self, obj):
        """Get reactions count summary."""
        if not obj.reactions:
            return {}
        return {emoji: len(users) for emoji, users in obj.reactions.items()}

    def get_is_edited(self, obj):
        """Check if message was edited."""
        return obj.edit_date is not None

    def get_can_edit(self, obj):
        """Check if current user can edit this message."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.can_be_edited(request.user)

    def get_can_delete(self, obj):
        """Check if current user can delete this message."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.can_be_deleted(request.user)

    def get_read_by(self, obj):
        """Get list of users who read this message (for small groups)."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return []

        # Only show read receipts for small groups/private chats
        if (
            obj.chat.type in [Chat.ChatType.PRIVATE, Chat.ChatType.GROUP]
            and obj.chat.get_participant_count() <= 20
        ):
            # This would need a separate model to track read receipts
            # For now, return empty list
            return []
        return []


class ChatParticipantSerializer(serializers.ModelSerializer):
    """
    Participant serializer with comprehensive permission handling.
    """

    user = UserBasicSerializer(read_only=True)
    is_admin = serializers.SerializerMethodField()
    is_moderator = serializers.SerializerMethodField()
    is_typing = serializers.SerializerMethodField()
    is_muted = serializers.SerializerMethodField()
    is_banned = serializers.SerializerMethodField()
    is_restricted = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField()

    class Meta:
        model = ChatParticipant
        fields = [
            "user",
            "role",
            "status",
            "custom_title",
            "is_admin",
            "is_moderator",
            "can_send_messages",
            "can_send_media",
            "can_send_stickers",
            "can_send_polls",
            "can_add_web_page_previews",
            "can_change_info",
            "can_invite_users",
            "can_pin_messages",
            "can_delete_messages",
            "can_ban_users",
            "can_restrict_members",
            "can_promote_members",
            "can_manage_calls",
            "is_anonymous",
            "notification_level",
            "folder",
            "unread_count",
            "unread_mentions_count",
            "is_typing",
            "is_muted",
            "is_banned",
            "is_restricted",
            "can_manage",
            "joined_at",
            "last_read_at",
            "last_activity_at",
        ]
        read_only_fields = [
            "joined_at",
            "last_read_at",
            "last_activity_at",
            "unread_count",
            "unread_mentions_count",
        ]

    def get_is_admin(self, obj):
        return obj.is_admin()

    def get_is_moderator(self, obj):
        return obj.is_moderator()

    def get_is_typing(self, obj):
        return obj.is_typing

    def get_is_muted(self, obj):
        return obj.is_muted

    def get_is_banned(self, obj):
        return obj.is_banned

    def get_is_restricted(self, obj):
        return obj.is_restricted

    def get_can_manage(self, obj):
        """Check if participant can manage the chat."""
        return obj.can_manage_chat


class ChatSerializer(serializers.ModelSerializer):
    """
    Comprehensive chat serializer with optimized queries.
    """

    creator = UserBasicSerializer(read_only=True)
    participants = serializers.SerializerMethodField()
    last_message = ChatMessageSerializer(read_only=True)
    pinned_message = ChatMessageSerializer(read_only=True)
    participant_count = serializers.SerializerMethodField()
    online_count = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    user_participant = serializers.SerializerMethodField()
    can_send_message = serializers.SerializerMethodField()
    is_member = serializers.SerializerMethodField()
    invite_link_info = serializers.SerializerMethodField()

    class Meta:
        model = Chat
        fields = [
            "id",
            "type",
            "name",
            "username",
            "description",
            "about",
            "photo",
            "photo_small",
            "creator",
            "status",
            "is_public",
            "is_verified",
            "is_scam",
            "is_fake",
            "max_members",
            "slow_mode_delay",
            "has_protected_content",
            "has_aggressive_anti_spam_enabled",
            "auto_delete_timer",
            "invite_link",
            "is_encrypted",
            "linked_project",
            "linked_task",
            "linked_network",
            "ai_enabled",
            "has_calls_enabled",
            "has_video_calls_enabled",
            "has_group_calls_enabled",
            "participants",
            "participant_count",
            "online_count",
            "messages_count",
            "last_message",
            "pinned_message",
            "unread_count",
            "user_participant",
            "can_send_message",
            "is_member",
            "invite_link_info",
            "theme",
            "wallpaper",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "creator",
            "messages_count",
            "created_at",
            "updated_at",
        ]

    def get_participants(self, obj):
        """Get participants with limit for performance."""
        # Always limit to 50 for performance
        participants = (
            obj.chatparticipant_set.select_related("user")
            .filter(status=ChatParticipant.ParticipantStatus.ACTIVE)
            .order_by("-role", "-joined_at")[:50]
        )

        return ChatParticipantSerializer(
            participants, many=True, context=self.context
        ).data

    def get_participant_count(self, obj):
        """Get cached participant count."""
        return obj.get_participant_count()

    def get_online_count(self, obj):
        """Get cached online count."""
        return obj.get_online_count()

    def get_unread_count(self, obj):
        """Get unread messages count for current user."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return 0

        try:
            participant = obj.chatparticipant_set.get(user=request.user)
            return participant.unread_count
        except ChatParticipant.DoesNotExist:
            return 0

    def get_user_participant(self, obj):
        """Get current user's participant info."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None

        try:
            participant = obj.chatparticipant_set.select_related("user").get(
                user=request.user
            )
            return ChatParticipantSerializer(participant, context=self.context).data
        except ChatParticipant.DoesNotExist:
            return None

    def get_can_send_message(self, obj):
        """Check if current user can send messages."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.can_user_send_message(request.user)

    def get_is_member(self, obj):
        """Check if current user is a member."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False

        return obj.chatparticipant_set.filter(
            user=request.user, status=ChatParticipant.ParticipantStatus.ACTIVE
        ).exists()

    def get_invite_link_info(self, obj):
        """Get invite link information if user has permission."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None

        try:
            participant = obj.chatparticipant_set.get(user=request.user)
            if participant.can_invite_users:
                return {
                    "link": obj.invite_link,
                    "can_create": True,
                }
        except ChatParticipant.DoesNotExist:
            pass

        return None


class ChatListSerializer(serializers.ModelSerializer):
    """
    Optimized serializer for chat lists with minimal data.
    """

    last_message = serializers.SerializerMethodField()
    participant_count = serializers.IntegerField(
        source="participants_count", read_only=True
    )
    unread_count = serializers.SerializerMethodField()
    is_member = serializers.SerializerMethodField()
    is_muted = serializers.SerializerMethodField()
    last_activity = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = Chat
        fields = [
            "id",
            "type",
            "name",
            "username",
            "photo",
            "status",
            "is_public",
            "is_verified",
            "is_muted",
            "participant_count",
            "last_message",
            "last_activity",
            "unread_count",
            "is_member",
        ]

    def get_last_message(self, obj):
        """Get simplified last message info."""
        if obj.last_message:
            return {
                "id": str(obj.last_message.id),
                "content": obj.last_message.content[:50]
                + ("..." if len(obj.last_message.content) > 50 else ""),
                "sender_name": (
                    obj.last_message.sender.get_full_name()
                    if obj.last_message.sender
                    else "System"
                ),
                "type": obj.last_message.type,
                "created_at": obj.last_message.created_at.isoformat(),
            }
        return None

    def get_unread_count(self, obj):
        """Get cached unread count."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return 0

        # Use caching for performance
        cache_key = f"unread_count_{obj.id}_{request.user.id}"
        count = cache.get(cache_key)

        if count is None:
            try:
                participant = obj.chatparticipant_set.get(user=request.user)
                count = participant.unread_count
            except ChatParticipant.DoesNotExist:
                count = 0
            cache.set(cache_key, count, 60)  # Cache for 1 minute

        return count

    def get_is_muted(self, obj):
        """Check if chat is muted for current user."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False

        try:
            participant = obj.chatparticipant_set.get(user=request.user)
            if participant.muted_until:
                return timezone.now() < participant.muted_until
            return False
        except ChatParticipant.DoesNotExist:
            return False

    def get_is_member(self, obj):
        """Check membership with caching."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False

        cache_key = f"is_member_{obj.id}_{request.user.id}"
        is_member = cache.get(cache_key)

        if is_member is None:
            is_member = obj.chatparticipant_set.filter(
                user=request.user, status=ChatParticipant.ParticipantStatus.ACTIVE
            ).exists()
            cache.set(cache_key, is_member, 300)  # Cache for 5 minutes

        return is_member


class ChatCreateSerializer(serializers.ModelSerializer):
    """
    Secure serializer for creating chats with validation.
    """

    participants = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
        help_text="List of user IDs to add as participants",
    )

    class Meta:
        model = Chat
        fields = [
            "id",
            "type",
            "name",
            "username",
            "description",
            "about",
            "photo",
            "is_public",
            "max_members",
            "participants",
            "linked_project",
            "linked_task",
            "linked_network",
            "ai_enabled",
            "has_calls_enabled",
            "slow_mode_delay",
            "auto_delete_timer",
        ]

    def validate_username(self, value):
        """Validate chat username with comprehensive checks."""
        if value:
            # Length validation
            if len(value) < 5 or len(value) > 32:
                raise serializers.ValidationError(
                    "Username must be between 5 and 32 characters"
                )

            # Character validation
            if not value.replace("_", "").isalnum():
                raise serializers.ValidationError(
                    "Username can only contain letters, numbers, and underscores"
                )

            # Uniqueness validation
            if Chat.objects.filter(username=value).exists():
                raise serializers.ValidationError("Username already exists")

            # Reserved usernames
            reserved = ["admin", "root", "support", "help", "api", "bot"]
            if value.lower() in reserved:
                raise serializers.ValidationError("This username is reserved")

        return value

    def validate_participants(self, value):
        """Validate participant user IDs with limits."""
        if not value:
            return []

        # Limit check
        if len(value) > 200:
            raise serializers.ValidationError(
                "Cannot add more than 200 participants at once"
            )

        # Validate all users exist and are active
        existing_users = User.objects.filter(id__in=value, is_active=True).values_list(
            "id", flat=True
        )

        if len(existing_users) != len(value):
            missing_count = len(value) - len(existing_users)
            raise serializers.ValidationError(
                f"{missing_count} users not found or inactive"
            )

        return value

    def validate_max_members(self, value):
        """Validate max members based on chat type."""
        chat_type = self.initial_data.get("type", Chat.ChatType.PRIVATE)

        if chat_type == Chat.ChatType.GROUP and value > 200:
            raise serializers.ValidationError(
                "Group chats cannot have more than 200 members"
            )
        elif chat_type == Chat.ChatType.SUPERGROUP and value > 200000:
            raise serializers.ValidationError(
                "Supergroups cannot have more than 200,000 members"
            )

        return value

    def validate(self, attrs):
        """Cross-field validation."""
        chat_type = attrs.get("type")
        username = attrs.get("username")
        name = attrs.get("name")
        is_public = attrs.get("is_public", False)

        # Type is required
        if not chat_type:
            raise serializers.ValidationError("Chat type is required")

        # Group chats must have a name
        if chat_type == Chat.ChatType.GROUP and not name:
            raise serializers.ValidationError("Group chats must have a name")

        # Public chats must have usernames
        if is_public and not username:
            raise serializers.ValidationError("Public chats must have a username")

        # Private chats cannot have usernames
        if chat_type == Chat.ChatType.PRIVATE and username:
            raise serializers.ValidationError("Private chats cannot have usernames")

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """Create chat with participants atomically."""
        participants_data = validated_data.pop("participants", [])
        user = self.context["request"].user

        # Create chat
        chat = Chat.objects.create(creator=user, **validated_data)

        # Add creator as owner
        ChatParticipant.objects.create(
            user=user, chat=chat, role=ChatParticipant.ParticipantRole.OWNER
        )

        # Add other participants
        participants_to_create = []
        for user_id in participants_data:
            try:
                participant_user = User.objects.get(id=user_id, is_active=True)
                participants_to_create.append(
                    ChatParticipant(
                        user=participant_user,
                        chat=chat,
                        role=ChatParticipant.ParticipantRole.MEMBER,
                    )
                )
            except User.DoesNotExist:
                continue

        # Bulk create participants for performance
        if participants_to_create:
            ChatParticipant.objects.bulk_create(participants_to_create)

        # Update participant count
        chat.participants_count = len(participants_to_create) + 1
        chat.save(update_fields=["participants_count"])

        return chat

    def to_representation(self, instance):
        """Custom representation to include creator info."""
        data = super().to_representation(instance)
        if hasattr(instance, "creator") and instance.creator:
            data["creator"] = {
                "id": str(instance.creator.id),
                "username": instance.creator.username,
                "first_name": instance.creator.first_name,
                "last_name": instance.creator.last_name,
            }
        return data


class MessageCreateSerializer(serializers.ModelSerializer):
    """
    Secure message creation serializer with comprehensive validation.
    """

    attachment_files = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=False,
        max_length=10,  # Max 10 files
        help_text="List of files to attach (max 10)",
    )
    reply_to_id = serializers.UUIDField(write_only=True, required=False)
    mention_user_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
        help_text="List of user IDs to mention",
    )

    class Meta:
        model = ChatMessage
        fields = [
            "type",
            "content",
            "reply_to_id",
            "mention_user_ids",
            "is_silent",
            "is_scheduled",
            "scheduled_date",
            "poll_data",
            "location_data",
            "contact_data",
            "attachment_files",
        ]

    def validate_content(self, value):
        """Validate message content."""
        if value:
            # Length validation
            if len(value) > 4096:
                raise serializers.ValidationError(
                    "Message content cannot exceed 4096 characters"
                )

            # Basic spam detection
            if value.count("http") > 5:
                raise serializers.ValidationError("Too many links in message")

            # XSS prevention - escape HTML content
            value = html.escape(value)

        return value

    def validate_reply_to_id(self, value):
        """Validate reply_to message exists and is accessible."""
        if value:
            chat = self.context.get("chat")
            try:
                message = ChatMessage.objects.get(id=value, chat=chat)
                # Check if message is not deleted
                if message.status == ChatMessage.MessageStatus.DELETED:
                    raise serializers.ValidationError("Cannot reply to deleted message")
            except ChatMessage.DoesNotExist:
                raise serializers.ValidationError(
                    "Reply message not found in this chat"
                )
        return value

    def validate_scheduled_date(self, value):
        """Validate scheduled date."""
        if value:
            if value <= timezone.now():
                raise serializers.ValidationError(
                    "Scheduled date must be in the future"
                )

            # Cannot schedule more than 1 year in advance
            if value > timezone.now() + timedelta(days=365):
                raise serializers.ValidationError(
                    "Cannot schedule more than 1 year in advance"
                )

        return value

    def validate_mention_user_ids(self, value):
        """Validate mentioned users are in the chat."""
        if value:
            chat = self.context.get("chat")
            valid_participants = chat.chatparticipant_set.filter(
                user_id__in=value, status=ChatParticipant.ParticipantStatus.ACTIVE
            ).values_list("user_id", flat=True)

            if len(valid_participants) != len(value):
                raise serializers.ValidationError(
                    "Some mentioned users are not in this chat"
                )

        return value

    def validate_attachment_files(self, value):
        """Validate attachment files."""
        if value:
            total_size = sum(file.size for file in value)
            if total_size > 200 * 1024 * 1024:  # 200MB total
                raise serializers.ValidationError(
                    "Total attachment size cannot exceed 200MB"
                )

        return value

    def validate(self, attrs):
        """Cross-field validation."""
        content = attrs.get("content", "")
        attachment_files = attrs.get("attachment_files", [])
        poll_data = attrs.get("poll_data")
        location_data = attrs.get("location_data")
        contact_data = attrs.get("contact_data")

        # Must have content or attachments or special data
        if not any(
            [content.strip(), attachment_files, poll_data, location_data, contact_data]
        ):
            raise serializers.ValidationError(
                "Message must have content, attachments, or special data"
            )

        # Check slow mode
        chat = self.context.get("chat")
        user = self.context.get("request").user

        if chat and chat.slow_mode_delay > 0:
            last_message = (
                ChatMessage.objects.filter(chat=chat, sender=user)
                .order_by("-created_at")
                .first()
            )

            if last_message:
                time_diff = (timezone.now() - last_message.created_at).total_seconds()
                if time_diff < chat.slow_mode_delay:
                    remaining = chat.slow_mode_delay - time_diff
                    raise serializers.ValidationError(
                        f"Slow mode: wait {remaining:.0f} seconds"
                    )

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """Create message with attachments and mentions."""
        attachment_files = validated_data.pop("attachment_files", [])
        reply_to_id = validated_data.pop("reply_to_id", None)
        mention_user_ids = validated_data.pop("mention_user_ids", [])

        # Get reply_to message if specified
        reply_to = None
        if reply_to_id:
            try:
                reply_to = ChatMessage.objects.get(
                    id=reply_to_id, chat=self.context["chat"]
                )
            except ChatMessage.DoesNotExist:
                pass

        # Create mentions data
        mentions = []
        if mention_user_ids:
            mentioned_users = User.objects.filter(id__in=mention_user_ids)
            mentions = [
                {"user_id": str(user.id), "username": user.username}
                for user in mentioned_users
            ]

        # Create message
        message = ChatMessage.objects.create(
            chat=self.context["chat"],
            sender=self.context["request"].user,
            reply_to=reply_to,
            has_media=bool(attachment_files),
            mentions=mentions,
            **validated_data,
        )

        # Create attachments
        attachments_to_create = []
        for file in attachment_files:
            # Calculate file checksum
            checksum = self._calculate_checksum(file)

            attachments_to_create.append(
                ChatAttachment(
                    message=message,
                    file=file,
                    file_name=file.name,
                    file_size=file.size,
                    mime_type=getattr(file, "content_type", ""),
                    type=self._determine_file_type(file),
                    checksum=checksum,
                )
            )

        if attachments_to_create:
            ChatAttachment.objects.bulk_create(attachments_to_create)

        return message

    def _determine_file_type(self, file):
        """Determine file type based on content type."""
        content_type = getattr(file, "content_type", "")

        if content_type.startswith("image/"):
            return ChatAttachment.AttachmentType.PHOTO
        elif content_type.startswith("video/"):
            return ChatAttachment.AttachmentType.VIDEO
        elif content_type.startswith("audio/"):
            return ChatAttachment.AttachmentType.AUDIO
        else:
            return ChatAttachment.AttachmentType.DOCUMENT

    def _calculate_checksum(self, file):
        """Calculate SHA256 checksum for file."""
        hash_sha256 = hashlib.sha256()
        for chunk in file.chunks():
            hash_sha256.update(chunk)
        return hash_sha256.hexdigest()


class ChatFolderSerializer(serializers.ModelSerializer):
    """
    Serializer for chat folders with validation.
    """

    chats_count = serializers.SerializerMethodField()
    chats = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Chat.objects.all(), required=False
    )

    class Meta:
        model = ChatFolder
        fields = [
            "id",
            "name",
            "emoji",
            "chats",
            "chats_count",
            "order",
            "include_private",
            "include_groups",
            "include_channels",
            "include_bots",
            "include_muted",
            "include_read",
            "include_archived",
            "contacts",
            "exclude_contacts",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_chats_count(self, obj):
        """Get count of chats matching folder criteria with caching."""
        cache_key = f"folder_chats_count_{obj.id}"
        count = cache.get(cache_key)

        if count is None:
            count = obj.get_chats_queryset().count()
            cache.set(cache_key, count, 300)  # 5 minutes cache

        return count

    def validate_name(self, value):
        """Validate folder name."""
        if len(value) > 100:
            raise serializers.ValidationError(
                "Folder name cannot exceed 100 characters"
            )
        return value

    def validate_chats(self, value):
        """Validate user has access to all specified chats."""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            user_chat_ids = Chat.objects.filter(participants=request.user).values_list(
                "id", flat=True
            )

            invalid_chats = [chat.id for chat in value if chat.id not in user_chat_ids]
            if invalid_chats:
                raise serializers.ValidationError(
                    "Cannot add chats you're not a member of"
                )

        return value


class ChatBotSerializer(serializers.ModelSerializer):
    """
    Serializer for chat bots with security validations.
    """

    user = UserBasicSerializer(read_only=True)
    commands_count = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = ChatBot
        fields = [
            "user",
            "description",
            "about",
            "bot_pic",
            "commands",
            "commands_count",
            "inline_placeholder",
            "is_inline",
            "can_join_groups",
            "can_read_all_group_messages",
            "supports_inline_queries",
            "webhook_url",
            "messages_sent",
            "users_count",
            "is_verified",
            "is_premium",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["user", "messages_sent", "users_count", "created_at"]

    def get_commands_count(self, obj):
        """Get count of bot commands."""
        return len(obj.commands) if obj.commands else 0

    def get_is_active(self, obj):
        """Check if bot is active."""
        return obj.user.is_active if obj.user else False

    def validate_webhook_url(self, value):
        """Validate webhook URL."""
        if value:
            if not value.startswith("https://"):
                raise serializers.ValidationError("Webhook URL must use HTTPS")
        return value

    def validate_commands(self, value):
        """Validate bot commands structure."""
        if value:
            if not isinstance(value, list):
                raise serializers.ValidationError("Commands must be a list")

            for command in value:
                if not isinstance(command, dict):
                    raise serializers.ValidationError(
                        "Each command must be a dictionary"
                    )

                required_fields = ["command", "description"]
                if not all(field in command for field in required_fields):
                    raise serializers.ValidationError(
                        "Commands must have 'command' and 'description' fields"
                    )

        return value


class ChatCallSerializer(serializers.ModelSerializer):
    """
    Serializer for chat calls with participant management.
    """

    initiator = UserBasicSerializer(read_only=True)
    participants = serializers.SerializerMethodField()
    duration_display = serializers.SerializerMethodField()
    participants_count = serializers.SerializerMethodField()
    can_join = serializers.SerializerMethodField()

    class Meta:
        model = ChatCall
        fields = [
            "id",
            "type",
            "status",
            "initiator",
            "participants",
            "participants_count",
            "max_participants",
            "start_time",
            "answer_time",
            "end_time",
            "duration",
            "duration_display",
            "quality_rating",
            "is_recorded",
            "recording_file",
            "is_video_disabled",
            "is_screen_sharing",
            "can_join",
        ]
        read_only_fields = [
            "id",
            "initiator",
            "start_time",
            "answer_time",
            "end_time",
            "duration",
        ]

    def get_participants(self, obj):
        """Get call participants with their status."""
        participants = obj.chatcallparticipant_set.select_related("user").all()
        return [
            {
                "user": UserBasicSerializer(p.user, context=self.context).data,
                "status": p.status,
                "joined_at": p.joined_at,
                "left_at": p.left_at,
                "is_muted": p.is_muted,
                "is_video_enabled": p.is_video_enabled,
            }
            for p in participants
        ]

    def get_duration_display(self, obj):
        """Get human readable duration."""
        return obj.get_duration_display()

    def get_participants_count(self, obj):
        """Get current participants count."""
        return obj.chatcallparticipant_set.filter(
            status=ChatCallParticipant.ParticipantStatus.JOINED
        ).count()

    def get_can_join(self, obj):
        """Check if current user can join the call."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False

        # Check if call is active
        if obj.status != ChatCall.CallStatus.ACTIVE:
            return False

        # Check if user is in the chat
        try:
            participant = obj.chat.chatparticipant_set.get(user=request.user)
            return participant.status == ChatParticipant.ParticipantStatus.ACTIVE
        except ChatParticipant.DoesNotExist:
            return False


class ChatPollSerializer(serializers.ModelSerializer):
    """
    Comprehensive poll serializer with voting logic.
    """

    options = serializers.SerializerMethodField()
    user_vote = serializers.SerializerMethodField()
    results = serializers.SerializerMethodField()
    can_vote = serializers.SerializerMethodField()

    class Meta:
        model = ChatPoll
        fields = [
            "id",
            "question",
            "type",
            "is_anonymous",
            "allows_multiple_answers",
            "is_closed",
            "correct_option_id",
            "explanation",
            "open_period",
            "close_date",
            "total_voter_count",
            "options",
            "user_vote",
            "results",
            "can_vote",
            "created_at",
        ]
        read_only_fields = ["id", "total_voter_count", "created_at"]

    def get_options(self, obj):
        """Get poll options with vote counts."""
        options = obj.chatpolloption_set.all().order_by("order")
        return [
            {
                "id": str(option.id),
                "text": option.text,
                "voter_count": option.voter_count,
                "order": option.order,
            }
            for option in options
        ]

    def get_user_vote(self, obj):
        """Get current user's vote."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None

        try:
            vote = obj.chatpollanswer_set.get(user=request.user)
            return vote.option_ids
        except ChatPollAnswer.DoesNotExist:
            return None

    def get_results(self, obj):
        """Get poll results based on visibility rules."""
        request = self.context.get("request")
        user = request.user if request and request.user.is_authenticated else None

        # Show results if poll is closed, user voted, or it's not anonymous
        show_results = (
            obj.is_closed
            or (user and obj.chatpollanswer_set.filter(user=user).exists())
            or not obj.is_anonymous
        )

        if not show_results:
            return None

        return obj.get_results()

    def get_can_vote(self, obj):
        """Check if current user can vote."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False

        # Check if poll is still open
        if obj.is_closed:
            return False

        # Check if user already voted (for single-answer polls)
        if not obj.allows_multiple_answers:
            if obj.chatpollanswer_set.filter(user=request.user).exists():
                return False

        return True


class ChatInviteLinkSerializer(serializers.ModelSerializer):
    """
    Secure invite link serializer with access control.
    """

    creator = UserBasicSerializer(read_only=True)
    is_valid = serializers.SerializerMethodField()
    usage_stats = serializers.SerializerMethodField()

    class Meta:
        model = ChatInviteLink
        fields = [
            "id",
            "link",
            "name",
            "creator",
            "expire_date",
            "member_limit",
            "creates_join_request",
            "is_primary",
            "is_revoked",
            "usage_count",
            "pending_join_request_count",
            "is_valid",
            "usage_stats",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "link",
            "creator",
            "usage_count",
            "pending_join_request_count",
            "created_at",
        ]

    def get_is_valid(self, obj):
        """Check if invite link is valid with caching."""
        cache_key = f"invite_valid_{obj.id}"
        is_valid = cache.get(cache_key)

        if is_valid is None:
            is_valid = obj.is_valid()
            cache.set(cache_key, is_valid, 60)  # 1 minute cache

        return is_valid

    def get_usage_stats(self, obj):
        """Get usage statistics for admins."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None

        # Only show stats to chat admins
        try:
            participant = obj.chat.chatparticipant_set.get(user=request.user)
            if participant.is_admin():
                return {
                    "total_uses": obj.usage_count,
                    "pending_requests": obj.pending_join_request_count,
                    "remaining_uses": (
                        max(0, obj.member_limit - obj.usage_count)
                        if obj.member_limit
                        else None
                    ),
                }
        except ChatParticipant.DoesNotExist:
            pass

        return None

    def validate_expire_date(self, value):
        """Validate expiration date."""
        if value and value <= timezone.now():
            raise serializers.ValidationError("Expiration date must be in the future")
        return value

    def validate_member_limit(self, value):
        """Validate member limit."""
        if value is not None and value < 1:
            raise serializers.ValidationError("Member limit must be at least 1")
        return value


class ChatJoinRequestSerializer(serializers.ModelSerializer):
    """
    Join request serializer with approval workflow.
    """

    user = UserBasicSerializer(read_only=True)
    chat = ChatListSerializer(read_only=True)
    approved_by = UserBasicSerializer(read_only=True)
    invite_link = ChatInviteLinkSerializer(read_only=True)
    can_approve = serializers.SerializerMethodField()

    class Meta:
        model = ChatJoinRequest
        fields = [
            "id",
            "user",
            "chat",
            "invite_link",
            "status",
            "bio",
            "approved_by",
            "can_approve",
            "created_at",
            "decided_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "chat",
            "approved_by",
            "created_at",
            "decided_at",
        ]

    def get_can_approve(self, obj):
        """Check if current user can approve this request."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False

        try:
            participant = obj.chat.chatparticipant_set.get(user=request.user)
            return (
                participant.can_invite_users
                and obj.status == ChatJoinRequest.RequestStatus.PENDING
            )
        except ChatParticipant.DoesNotExist:
            return False


class ChatModerationLogSerializer(serializers.ModelSerializer):
    """
    Moderation log serializer for audit trails.
    """

    moderator = UserBasicSerializer(read_only=True)
    target_user = UserBasicSerializer(read_only=True)
    target_message = serializers.SerializerMethodField()
    action_display = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = ChatModerationLog
        fields = [
            "id",
            "action",
            "action_display",
            "moderator",
            "target_user",
            "target_message",
            "reason",
            "duration",
            "old_value",
            "new_value",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_target_message(self, obj):
        """Get simplified target message info."""
        if obj.target_message:
            return {
                "id": str(obj.target_message.id),
                "content": obj.target_message.content[:100]
                + ("..." if len(obj.target_message.content) > 100 else ""),
                "type": obj.target_message.type,
                "created_at": obj.target_message.created_at.isoformat(),
            }
        return None


class ChatStickerSetSerializer(serializers.ModelSerializer):
    """
    Sticker set serializer with installation tracking.
    """

    creator = UserBasicSerializer(read_only=True)
    stickers_count = serializers.SerializerMethodField()
    is_installed = serializers.SerializerMethodField()
    preview_stickers = serializers.SerializerMethodField()

    class Meta:
        model = ChatStickerSet
        fields = [
            "id",
            "name",
            "title",
            "type",
            "creator",
            "thumb",
            "is_official",
            "is_masks",
            "is_premium",
            "install_count",
            "stickers_count",
            "is_installed",
            "preview_stickers",
            "created_at",
        ]
        read_only_fields = ["id", "install_count", "created_at"]

    def get_stickers_count(self, obj):
        """Get cached stickers count."""
        cache_key = f"sticker_set_count_{obj.id}"
        count = cache.get(cache_key)

        if count is None:
            count = obj.get_stickers_count()
            cache.set(cache_key, count, 3600)  # 1 hour cache

        return count

    def get_is_installed(self, obj):
        """Check if current user has installed this sticker set."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False

        return UserStickerSet.objects.filter(
            user=request.user, sticker_set=obj
        ).exists()

    def get_preview_stickers(self, obj):
        """Get preview stickers (first 5)."""
        stickers = obj.chatsticker_set.all()[:5]
        return ChatStickerSerializer(stickers, many=True, context=self.context).data


class ChatStickerSerializer(serializers.ModelSerializer):
    """
    Individual sticker serializer with usage tracking.
    """

    file_url = serializers.SerializerMethodField()
    thumb_url = serializers.SerializerMethodField()

    class Meta:
        model = ChatSticker
        fields = [
            "id",
            "sticker_set",
            "file",
            "file_url",
            "thumb",
            "thumb_url",
            "emoji",
            "width",
            "height",
            "file_size",
            "mask_position",
            "is_premium",
            "order",
        ]
        read_only_fields = ["id", "file_size"]

    def get_file_url(self, obj):
        """Get sticker file URL."""
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None

    def get_thumb_url(self, obj):
        """Get sticker thumbnail URL."""
        if obj.thumb:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.thumb.url)
            return obj.thumb.url
        return None


class ChatThemeSerializer(serializers.ModelSerializer):
    """
    Chat theme serializer with validation.
    """

    is_using = serializers.SerializerMethodField()

    class Meta:
        model = ChatTheme
        fields = [
            "id",
            "name",
            "title",
            "accent_color",
            "background_color",
            "text_color",
            "background_image",
            "pattern_image",
            "is_dark",
            "is_premium",
            "is_default",
            "is_using",
            "settings",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_is_using(self, obj):
        """Check if current user is using this theme."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False

        # This would require a user preference model
        # For now, return False
        return False

    def validate_accent_color(self, value):
        """Validate hex color format."""
        if value and not value.startswith("#"):
            raise serializers.ValidationError(
                "Color must be in hex format (e.g., #FF0000)"
            )
        return value


# Bulk operation serializers
class BulkMessageReadSerializer(serializers.Serializer):
    """
    Serializer for marking multiple messages as read with validation.
    """

    message_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        max_length=100,  # Limit bulk operations
    )

    def validate_message_ids(self, value):
        """Validate user has access to all messages."""
        request = self.context.get("request")
        chat = self.context.get("chat")

        if request and chat:
            # Check if user is participant
            try:
                participant = chat.chatparticipant_set.get(user=request.user)
                if participant.status != ChatParticipant.ParticipantStatus.ACTIVE:
                    raise serializers.ValidationError("Not an active participant")
            except ChatParticipant.DoesNotExist:
                raise serializers.ValidationError("Not a member of this chat")

            # Validate all messages exist in this chat
            existing_count = ChatMessage.objects.filter(id__in=value, chat=chat).count()

            if existing_count != len(value):
                raise serializers.ValidationError(
                    "Some messages not found in this chat"
                )

        return value


class BulkMessageDeleteSerializer(serializers.Serializer):
    """
    Serializer for deleting multiple messages with permission checks.
    """

    message_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        max_length=50,  # Smaller limit for deletions
    )
    delete_for_everyone = serializers.BooleanField(default=False)

    def validate(self, attrs):
        """Validate deletion permissions."""
        request = self.context.get("request")
        chat = self.context.get("chat")
        message_ids = attrs.get("message_ids", [])
        delete_for_everyone = attrs.get("delete_for_everyone", False)

        if request and chat:
            try:
                participant = chat.chatparticipant_set.get(user=request.user)

                # Check basic permissions
                if participant.status != ChatParticipant.ParticipantStatus.ACTIVE:
                    raise serializers.ValidationError("Not an active participant")

                # Get messages to delete
                messages = ChatMessage.objects.filter(id__in=message_ids, chat=chat)

                for message in messages:
                    if delete_for_everyone:
                        # Check admin permissions for delete for everyone
                        if not participant.can_delete_messages:
                            raise serializers.ValidationError(
                                "No permission to delete for everyone"
                            )
                    else:
                        # Check if user can delete own messages
                        if message.sender != request.user:
                            raise serializers.ValidationError(
                                "Can only delete own messages"
                            )

            except ChatParticipant.DoesNotExist:
                raise serializers.ValidationError("Not a member of this chat")

        return attrs


class ChatSearchSerializer(serializers.Serializer):
    """
    Enhanced serializer for chat search with filters.
    """

    query = serializers.CharField(max_length=100, help_text="Search query")
    chat_types = serializers.ListField(
        child=serializers.ChoiceField(choices=Chat.ChatType.choices),
        required=False,
        help_text="Filter by chat types",
    )
    include_messages = serializers.BooleanField(
        default=False, help_text="Include message content in search"
    )
    date_from = serializers.DateTimeField(
        required=False, help_text="Search from this date"
    )
    date_to = serializers.DateTimeField(
        required=False, help_text="Search until this date"
    )
    limit = serializers.IntegerField(
        default=20, min_value=1, max_value=100, help_text="Number of results to return"
    )
    offset = serializers.IntegerField(
        default=0, min_value=0, help_text="Offset for pagination"
    )

    def validate(self, attrs):
        """Validate date range."""
        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")

        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError("date_from cannot be after date_to")

        return attrs


class MessageSearchSerializer(serializers.Serializer):
    """
    Enhanced serializer for message search with comprehensive filters.
    """

    query = serializers.CharField(max_length=100, help_text="Search query")
    message_types = serializers.ListField(
        child=serializers.ChoiceField(choices=ChatMessage.MessageType.choices),
        required=False,
        help_text="Filter by message types",
    )
    sender_id = serializers.IntegerField(required=False, help_text="Filter by sender")
    has_media = serializers.BooleanField(
        required=False, help_text="Filter messages with media"
    )
    date_from = serializers.DateTimeField(
        required=False, help_text="Search from this date"
    )
    date_to = serializers.DateTimeField(
        required=False, help_text="Search until this date"
    )
    in_thread = serializers.BooleanField(
        default=False, help_text="Search only in message threads"
    )
    limit = serializers.IntegerField(
        default=50, min_value=1, max_value=200, help_text="Number of results to return"
    )
    offset = serializers.IntegerField(
        default=0, min_value=0, help_text="Offset for pagination"
    )

    def validate(self, attrs):
        """Validate search parameters."""
        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")

        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError("date_from cannot be after date_to")

        return attrs


# Additional utility serializers
class MessageEditSerializer(serializers.Serializer):
    """
    Serializer for editing messages.
    """

    content = serializers.CharField(max_length=4096)

    def validate_content(self, value):
        """Validate edited content."""
        if not value.strip():
            raise serializers.ValidationError("Content cannot be empty")
        return value


class ChatSettingsSerializer(serializers.Serializer):
    """
    Serializer for updating chat settings.
    """

    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(max_length=255, required=False)
    photo = serializers.ImageField(required=False)
    slow_mode_delay = serializers.ChoiceField(
        choices=Chat.SlowModeInterval.choices, required=False
    )
    auto_delete_timer = serializers.IntegerField(min_value=0, required=False)

    def validate_name(self, value):
        """Validate chat name."""
        if value and len(value.strip()) < 1:
            raise serializers.ValidationError("Chat name cannot be empty")
        return value


class ParticipantPermissionSerializer(serializers.Serializer):
    """
    Serializer for updating participant permissions.
    """

    can_send_messages = serializers.BooleanField(required=False)
    can_send_media = serializers.BooleanField(required=False)
    can_send_stickers = serializers.BooleanField(required=False)
    can_send_polls = serializers.BooleanField(required=False)
    can_add_web_page_previews = serializers.BooleanField(required=False)
    can_change_info = serializers.BooleanField(required=False)
    can_invite_users = serializers.BooleanField(required=False)
    can_pin_messages = serializers.BooleanField(required=False)
    can_delete_messages = serializers.BooleanField(required=False)
    can_ban_users = serializers.BooleanField(required=False)
    can_restrict_members = serializers.BooleanField(required=False)
    can_promote_members = serializers.BooleanField(required=False)
    can_manage_calls = serializers.BooleanField(required=False)
    custom_title = serializers.CharField(
        max_length=16, required=False, allow_blank=True
    )

    def validate_custom_title(self, value):
        """Validate custom title length."""
        if value and len(value) > 16:
            raise serializers.ValidationError(
                "Custom title cannot exceed 16 characters"
            )
        return value


class ReactionToggleSerializer(serializers.Serializer):
    """
    Serializer for toggling message reactions.
    """

    emoji = serializers.CharField(max_length=10)

    def validate_emoji(self, value):
        """Validate emoji format."""
        if not value:
            raise serializers.ValidationError("Emoji is required")
        # Basic emoji validation - could be enhanced with emoji library
        return value


class PollVoteSerializer(serializers.Serializer):
    """
    Serializer for voting in polls.
    """

    option_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=10,  # Max 10 options for multiple choice
    )

    def validate_option_ids(self, value):
        """Validate poll options exist."""
        poll = self.context.get("poll")
        if poll:
            valid_options = poll.chatpolloption_set.values_list("id", flat=True)
            invalid_options = [
                opt_id for opt_id in value if opt_id not in valid_options
            ]

            if invalid_options:
                raise serializers.ValidationError("Some poll options are invalid")

            # Check if multiple answers are allowed
            if not poll.allows_multiple_answers and len(value) > 1:
                raise serializers.ValidationError(
                    "This poll only allows single answers"
                )

        return value


class CallActionSerializer(serializers.Serializer):
    """
    Serializer for call actions (join, leave, mute, etc.).
    """

    action = serializers.ChoiceField(
        choices=[
            "join",
            "leave",
            "mute",
            "unmute",
            "enable_video",
            "disable_video",
            "start_screen_share",
            "stop_screen_share",
        ]
    )

    def validate_action(self, value):
        """Validate action is allowed."""
        call = self.context.get("call")
        user = self.context.get("user")

        if call and user:
            # Basic validation - could be enhanced based on call state
            if value == "join" and call.status != ChatCall.CallStatus.ACTIVE:
                raise serializers.ValidationError("Cannot join inactive call")

        return value


class FileUploadSerializer(serializers.Serializer):
    """
    Dedicated file upload serializer with security checks.
    """

    file = serializers.FileField()
    caption = serializers.CharField(max_length=1024, required=False, allow_blank=True)

    def validate_file(self, value):
        """Comprehensive file validation."""
        # Size validation (100MB max)
        if value.size > 100 * 1024 * 1024:
            raise serializers.ValidationError("File size cannot exceed 100MB")

        # Content type validation
        content_type = getattr(value, "content_type", "")
        allowed_types = [
            "image/",
            "video/",
            "audio/",
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument",
            "text/",
            "application/zip",
            "application/x-rar",
        ]

        if not any(content_type.startswith(allowed) for allowed in allowed_types):
            raise serializers.ValidationError("File type not allowed")

        # Filename validation
        dangerous_extensions = [".exe", ".scr", ".bat", ".cmd", ".com", ".pif", ".jar"]
        if any(value.name.lower().endswith(ext) for ext in dangerous_extensions):
            raise serializers.ValidationError(
                "File type not allowed for security reasons"
            )

        return value


class ChatExportSerializer(serializers.Serializer):
    """
    Serializer for exporting chat data.
    """

    format = serializers.ChoiceField(choices=["json", "html", "txt"])
    include_media = serializers.BooleanField(default=False)
    date_from = serializers.DateTimeField(required=False)
    date_to = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        """Validate export parameters."""
        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")

        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError("date_from cannot be after date_to")

        return attrs


class ChatAnalyticsSerializer(serializers.Serializer):
    """
    Serializer for chat analytics data.
    """

    period = serializers.ChoiceField(choices=["day", "week", "month", "year"])
    metrics = serializers.ListField(
        child=serializers.ChoiceField(
            choices=["messages", "participants", "media_files", "calls", "reactions"]
        ),
        required=False,
    )

    def validate_period(self, value):
        """Validate analytics period."""
        # Additional validation can be added here
        return value


# Nested serializers for complex data structures
class LocationDataSerializer(serializers.Serializer):
    """
    Serializer for location data in messages.
    """

    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    address = serializers.CharField(max_length=255, required=False)
    venue_name = serializers.CharField(max_length=100, required=False)

    def validate_latitude(self, value):
        """Validate latitude range."""
        if not -90 <= value <= 90:
            raise serializers.ValidationError("Latitude must be between -90 and 90")
        return value

    def validate_longitude(self, value):
        """Validate longitude range."""
        if not -180 <= value <= 180:
            raise serializers.ValidationError("Longitude must be between -180 and 180")
        return value


class ContactDataSerializer(serializers.Serializer):
    """
    Serializer for contact data in messages.
    """

    phone_number = serializers.CharField(max_length=20)
    first_name = serializers.CharField(max_length=50)
    last_name = serializers.CharField(max_length=50, required=False)
    user_id = serializers.IntegerField(required=False)

    def validate_phone_number(self, value):
        """Basic phone number validation."""
        import re

        if not re.match(r"^\+?[1-9]\d{1,14}$", value):
            raise serializers.ValidationError("Invalid phone number format")
        return value


class ChatStatisticsSerializer(serializers.Serializer):
    """
    Read-only serializer for chat statistics.
    """

    total_messages = serializers.IntegerField(read_only=True)
    total_participants = serializers.IntegerField(read_only=True)
    online_participants = serializers.IntegerField(read_only=True)
    messages_today = serializers.IntegerField(read_only=True)
    media_messages = serializers.IntegerField(read_only=True)
    most_active_users = serializers.ListField(read_only=True)
    peak_activity_hour = serializers.IntegerField(read_only=True)


# WebSocket event serializers
class TypingEventSerializer(serializers.Serializer):
    """
    Serializer for typing indicator events.
    """

    chat_id = serializers.UUIDField()
    is_typing = serializers.BooleanField()

    def validate_chat_id(self, value):
        """Validate chat exists and user has access."""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            try:
                chat = Chat.objects.get(id=value)
                participant = chat.chatparticipant_set.get(user=request.user)
                if participant.status != ChatParticipant.ParticipantStatus.ACTIVE:
                    raise serializers.ValidationError("Not an active chat member")
            except (Chat.DoesNotExist, ChatParticipant.DoesNotExist):
                raise serializers.ValidationError("Chat not found or no access")
        return value


class OnlineStatusSerializer(serializers.Serializer):
    """
    Serializer for online status updates.
    """

    is_online = serializers.BooleanField()
    last_seen = serializers.DateTimeField(read_only=True)


class ChatPreviewSerializer(serializers.ModelSerializer):
    """
    Minimal chat serializer for previews and search results.
    """

    participant_count = serializers.IntegerField(
        source="participants_count", read_only=True
    )

    class Meta:
        model = Chat
        fields = [
            "id",
            "name",
            "type",
            "photo",
            "username",
            "is_public",
            "is_verified",
            "participant_count",
        ]


class MessagePreviewSerializer(serializers.ModelSerializer):
    """
    Minimal message serializer for search results and previews.
    """

    sender_name = serializers.CharField(source="sender.get_full_name", read_only=True)

    class Meta:
        model = ChatMessage
        fields = ["id", "content", "type", "sender_name", "created_at", "has_media"]

    def to_representation(self, instance):
        """Limit content length for previews."""
        data = super().to_representation(instance)
        if data.get("content"):
            data["content"] = data["content"][:150] + (
                "..." if len(data["content"]) > 150 else ""
            )
        return data
