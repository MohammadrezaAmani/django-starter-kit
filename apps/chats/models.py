import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from encrypted_model_fields.fields import EncryptedTextField

User = get_user_model()


class ChatQuerySet(models.QuerySet):
    """Custom QuerySet for Chat model with performance optimizations."""

    def active(self):
        return self.filter(status=Chat.ChatStatus.ACTIVE)

    def for_user(self, user):
        return self.filter(participants=user)

    def with_unread_count(self, user):
        return self.annotate(
            user_unread_count=Count(
                "messages",
                filter=Q(
                    messages__created_at__gt=models.Subquery(
                        ChatParticipant.objects.filter(
                            chat=models.OuterRef("pk"), user=user
                        ).values("last_read_at")[:1]
                    )
                ),
            )
        )

    def with_last_message(self):
        return self.select_related("last_message__sender").prefetch_related(
            "last_message__attachments"
        )


class Chat(models.Model):
    """
    Unified model for all chat types with advanced features.
    Supports performance optimizations and security features.
    """

    class ChatType(models.TextChoices):
        PRIVATE = "private", _("Private Chat")
        GROUP = "group", _("Group Chat")  # Up to 200 members
        SUPERGROUP = "supergroup", _("Supergroup")  # Up to 200k members
        CHANNEL = "channel", _("Channel")  # Broadcast only
        SECRET = "secret", _("Secret Chat")  # E2E encrypted
        BOT = "bot", _("Bot Chat")
        FORUM = "forum", _("Forum")  # Topic-based discussions

    class ChatStatus(models.TextChoices):
        ACTIVE = "active", _("Active")
        ARCHIVED = "archived", _("Archived")
        MUTED = "muted", _("Muted")
        DELETED = "deleted", _("Deleted")
        RESTRICTED = "restricted", _("Restricted")

    class SlowModeInterval(models.IntegerChoices):
        DISABLED = 0, _("Disabled")
        SECONDS_10 = 10, _("10 seconds")
        SECONDS_30 = 30, _("30 seconds")
        MINUTE_1 = 60, _("1 minute")
        MINUTES_5 = 300, _("5 minutes")
        MINUTES_15 = 900, _("15 minutes")
        HOUR_1 = 3600, _("1 hour")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(
        max_length=20, choices=ChatType.choices, default=ChatType.PRIVATE
    )
    name = models.CharField(max_length=255, blank=True, db_index=True)
    description = models.TextField(blank=True, max_length=255)
    about = models.TextField(
        blank=True, max_length=70
    )  # Short description for channels
    photo = models.ImageField(upload_to="chat_photos/", blank=True, null=True)
    photo_small = models.ImageField(
        upload_to="chat_photos/small/", blank=True, null=True
    )

    # Ownership and Management
    creator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="chats_created",
        db_index=True,
    )
    participants = models.ManyToManyField(
        User, through="ChatParticipant", related_name="chats"
    )

    # Status and Settings
    status = models.CharField(
        max_length=20,
        choices=ChatStatus.choices,
        default=ChatStatus.ACTIVE,
        db_index=True,
    )
    is_public = models.BooleanField(default=False)  # Public groups/channels
    is_verified = models.BooleanField(default=False)  # Verified badge
    is_scam = models.BooleanField(default=False)  # Marked as scam
    is_fake = models.BooleanField(default=False)  # Marked as fake

    # Permissions and Limits
    max_members = models.PositiveIntegerField(default=200)
    slow_mode_delay = models.PositiveIntegerField(
        choices=SlowModeInterval.choices, default=SlowModeInterval.DISABLED
    )

    # Features
    has_protected_content = models.BooleanField(
        default=False
    )  # Disable forwarding/saving
    has_aggressive_anti_spam_enabled = models.BooleanField(default=False)
    auto_delete_timer = models.PositiveIntegerField(
        null=True, blank=True
    )  # Auto-delete messages after N seconds

    # Invite and Discovery
    invite_link = models.CharField(max_length=100, blank=True, unique=True, null=True)
    username = models.CharField(
        max_length=32, blank=True, unique=True, null=True, db_index=True
    )  # Public username

    # Encryption (for secret chats)
    is_encrypted = models.BooleanField(default=False)
    encryption_key_fingerprint = models.CharField(max_length=64, blank=True)

    # Integrations with existing models
    linked_project = models.ForeignKey(
        "accounts.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="project_chats",
    )
    linked_task = models.ForeignKey(
        "accounts.Task",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_chats",
    )
    linked_network = models.ForeignKey(
        "accounts.Network",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="network_chats",
    )

    # AI and Bot Features
    ai_enabled = models.BooleanField(default=False)
    bot_commands = models.JSONField(default=list, blank=True)

    # Call Features
    has_calls_enabled = models.BooleanField(default=True)
    has_video_calls_enabled = models.BooleanField(default=True)
    has_group_calls_enabled = models.BooleanField(default=True)

    # Statistics and Performance
    messages_count = models.PositiveIntegerField(default=0)
    participants_count = models.PositiveIntegerField(default=0)
    online_count = models.PositiveIntegerField(default=0)

    # Message Management
    last_message = models.ForeignKey(
        "ChatMessage",
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        blank=True,
    )
    pinned_message = models.ForeignKey(
        "ChatMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pinned_in_chats",
    )

    # Theming
    theme = models.JSONField(default=dict, blank=True)
    wallpaper = models.ImageField(upload_to="chat_wallpapers/", blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    objects = ChatQuerySet.as_manager()

    class Meta:
        verbose_name = _("Chat")
        verbose_name_plural = _("Chats")
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["type", "status"]),
            models.Index(fields=["creator", "created_at"]),
            models.Index(fields=["is_public", "type"]),
            models.Index(fields=["username"]),
            models.Index(fields=["updated_at"]),
        ]

    def __str__(self):
        return self.name or f"{self.get_type_display()} ({str(self.id)[:8]})"

    @property
    def is_group(self):
        return self.type in [self.ChatType.GROUP, self.ChatType.SUPERGROUP]

    @property
    def is_channel(self):
        return self.type == self.ChatType.CHANNEL

    @property
    def is_forum(self):
        return self.type == self.ChatType.FORUM

    def get_participant_count(self):
        """Get cached participant count."""
        cache_key = f"chat_participants_{self.id}"
        count = cache.get(cache_key)
        if count is None:
            count = self.participants.filter(
                chatparticipant__status=ChatParticipant.ParticipantStatus.ACTIVE
            ).count()
            cache.set(cache_key, count, 300)  # 5 minutes cache
        return count

    def get_online_count(self):
        """Get online participants count."""
        five_minutes_ago = timezone.now() - timedelta(minutes=5)
        return self.participants.filter(
            last_activity__gte=five_minutes_ago,
            chatparticipant__status=ChatParticipant.ParticipantStatus.ACTIVE,
        ).count()

    def generate_invite_link(self):
        """Generate unique invite link."""
        if not self.invite_link:
            self.invite_link = uuid.uuid4().hex[:16]
            self.save(update_fields=["invite_link"])
        return self.invite_link

    def can_user_send_message(self, user):
        """Check if user can send messages to this chat."""
        if self.type == self.ChatType.CHANNEL:
            # Only admins can send to channels
            try:
                participant = self.chatparticipant_set.get(user=user)
                return participant.is_admin()
            except ChatParticipant.DoesNotExist:
                return False

        try:
            participant = self.chatparticipant_set.get(user=user)
            return (
                participant.can_send_messages
                and participant.status == ChatParticipant.ParticipantStatus.ACTIVE
            )
        except ChatParticipant.DoesNotExist:
            return False


class ChatParticipant(models.Model):
    """
    Through model for chat participants with comprehensive permissions.
    """

    class ParticipantRole(models.TextChoices):
        OWNER = "owner", _("Owner")
        ADMIN = "admin", _("Administrator")
        MODERATOR = "moderator", _("Moderator")
        MEMBER = "member", _("Member")
        RESTRICTED = "restricted", _("Restricted")
        GUEST = "guest", _("Guest")
        BOT = "bot", _("Bot")

    class ParticipantStatus(models.TextChoices):
        ACTIVE = "active", _("Active")
        LEFT = "left", _("Left")
        KICKED = "kicked", _("Kicked")
        BANNED = "banned", _("Banned")
        RESTRICTED = "restricted", _("Restricted")

    class NotificationLevel(models.TextChoices):
        ALL = "all", _("All Messages")
        MENTIONS = "mentions", _("Mentions Only")
        DISABLED = "disabled", _("Disabled")

    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, db_index=True)

    # Role and Status
    role = models.CharField(
        max_length=20, choices=ParticipantRole.choices, default=ParticipantRole.MEMBER
    )
    status = models.CharField(
        max_length=20,
        choices=ParticipantStatus.choices,
        default=ParticipantStatus.ACTIVE,
    )
    custom_title = models.CharField(max_length=16, blank=True)  # Admin custom title

    # Permissions
    can_send_messages = models.BooleanField(default=True)
    can_send_media = models.BooleanField(default=True)
    can_send_stickers = models.BooleanField(default=True)
    can_send_polls = models.BooleanField(default=True)
    can_send_other = models.BooleanField(default=True)  # Games, inline bots, etc.
    can_add_web_page_previews = models.BooleanField(default=True)
    can_change_info = models.BooleanField(default=False)
    can_invite_users = models.BooleanField(default=False)
    can_pin_messages = models.BooleanField(default=False)
    can_delete_messages = models.BooleanField(default=False)
    can_ban_users = models.BooleanField(default=False)
    can_restrict_members = models.BooleanField(default=False)
    can_promote_members = models.BooleanField(default=False)
    can_manage_calls = models.BooleanField(default=False)
    can_manage_topics = models.BooleanField(default=False)  # For forum chats
    can_post_messages = models.BooleanField(default=False)  # For channels
    can_edit_messages = models.BooleanField(default=False)  # For channels
    is_anonymous = models.BooleanField(default=False)  # Admin anonymity

    # User Preferences
    notification_level = models.CharField(
        max_length=20, choices=NotificationLevel.choices, default=NotificationLevel.ALL
    )
    muted_until = models.DateTimeField(null=True, blank=True)
    folder = models.CharField(max_length=50, blank=True)

    # Read Status
    last_read_message_id = models.UUIDField(null=True, blank=True)
    last_read_at = models.DateTimeField(null=True, blank=True, db_index=True)
    unread_count = models.PositiveIntegerField(default=0)
    unread_mentions_count = models.PositiveIntegerField(default=0)

    # Activity Tracking
    joined_at = models.DateTimeField(auto_now_add=True, db_index=True)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    typing_until = models.DateTimeField(null=True, blank=True)  # Typing indicator

    # Restrictions
    banned_until = models.DateTimeField(null=True, blank=True)
    restricted_until = models.DateTimeField(null=True, blank=True)
    ban_reason = models.TextField(blank=True)

    # Device Management
    devices = models.JSONField(default=list, blank=True)  # Multi-device sync

    class Meta:
        verbose_name = _("Chat Participant")
        verbose_name_plural = _("Chat Participants")
        unique_together = [["user", "chat"]]
        indexes = [
            models.Index(fields=["user", "chat"]),
            models.Index(fields=["chat", "role"]),
            models.Index(fields=["status", "joined_at"]),
            models.Index(fields=["last_read_at"]),
        ]

    def __str__(self):
        return f"{self.user.username} in {self.chat.name or self.chat.id}"

    def is_admin(self):
        return self.role in [self.ParticipantRole.OWNER, self.ParticipantRole.ADMIN]

    def is_moderator(self):
        return self.role in [
            self.ParticipantRole.OWNER,
            self.ParticipantRole.ADMIN,
            self.ParticipantRole.MODERATOR,
        ]

    @property
    def can_manage_chat(self):
        return self.is_admin() and self.can_change_info

    def update_last_read(self, message=None):
        """Update last read message and timestamp."""
        self.last_read_at = timezone.now()
        if message:
            # Handle both message objects and message IDs
            if hasattr(message, "id"):
                self.last_read_message_id = message.id
            else:
                self.last_read_message_id = message
        self.unread_count = 0
        self.save(
            update_fields=["last_read_at", "last_read_message_id", "unread_count"]
        )

    def set_typing(self, duration_seconds=5):
        """Set typing indicator."""
        self.typing_until = timezone.now() + timedelta(seconds=duration_seconds)
        self.save(update_fields=["typing_until"])

    @property
    def is_typing(self):
        """Check if user is currently typing."""
        if not self.typing_until:
            return False
        return timezone.now() < self.typing_until

    @property
    def is_muted(self):
        """Check if participant has muted the chat."""
        if not self.muted_until:
            return self.notification_level == self.NotificationLevel.DISABLED
        return timezone.now() < self.muted_until

    @property
    def is_banned(self):
        """Check if participant is currently banned."""
        if self.status == self.ParticipantStatus.BANNED:
            if not self.banned_until:
                return True
            return timezone.now() < self.banned_until
        return False

    @property
    def is_restricted(self):
        """Check if participant is currently restricted."""
        if self.status == self.ParticipantStatus.RESTRICTED:
            if not self.restricted_until:
                return True
            return timezone.now() < self.restricted_until
        return False


class ChatMessageQuerySet(models.QuerySet):
    """Custom QuerySet for ChatMessage with performance optimizations."""

    def visible(self):
        return self.exclude(status=ChatMessage.MessageStatus.DELETED)

    def for_user(self, user, chat=None):
        """Get messages visible to a specific user."""
        if chat:
            participant = ChatParticipant.objects.filter(user=user, chat=chat).first()
            if not participant:
                return self.none()
            queryset = self.filter(chat=chat, created_at__gte=participant.joined_at)
        else:
            # Get all messages from chats where user is a participant
            user_chats = Chat.objects.filter(participants=user)
            queryset = self.filter(chat__in=user_chats)

        return queryset.visible()

    def with_attachments(self):
        return self.prefetch_related("attachments")

    def unread_for_user(self, user, chat):
        participant = ChatParticipant.objects.filter(user=user, chat=chat).first()
        if not participant or not participant.last_read_at:
            return self.filter(chat=chat)
        return self.filter(chat=chat, created_at__gt=participant.last_read_at)


class ChatMessage(models.Model):
    """
    Comprehensive message model supporting all message types and features.
    """

    class MessageType(models.TextChoices):
        TEXT = "text", _("Text")
        PHOTO = "photo", _("Photo")
        VIDEO = "video", _("Video")
        AUDIO = "audio", _("Audio")
        VOICE = "voice", _("Voice Note")
        VIDEO_NOTE = "video_note", _("Video Note")
        DOCUMENT = "document", _("Document")
        STICKER = "sticker", _("Sticker")
        ANIMATION = "animation", _("GIF/Animation")
        POLL = "poll", _("Poll")
        QUIZ = "quiz", _("Quiz")
        LOCATION = "location", _("Location")
        VENUE = "venue", _("Venue")
        CONTACT = "contact", _("Contact")
        GAME = "game", _("Game")
        INVOICE = "invoice", _("Invoice")
        PAYMENT = "payment", _("Payment")
        DICE = "dice", _("Dice")
        SYSTEM = "system", _("System Message")
        SERVICE = "service", _("Service Message")
        CALL = "call", _("Call")
        STORY = "story", _("Story")

    class MessageStatus(models.TextChoices):
        SENDING = "sending", _("Sending")
        SENT = "sent", _("Sent")
        RECEIVED = "received", _("Received")
        READ = "read", _("Read")
        EDITED = "edited", _("Edited")
        DELETED = "deleted", _("Deleted")
        FAILED = "failed", _("Failed")
        SCHEDULED = "scheduled", _("Scheduled")

    class DeleteType(models.TextChoices):
        FOR_ME = "for_me", _("Delete for me")
        FOR_EVERYONE = "for_everyone", _("Delete for everyone")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Core References
    chat = models.ForeignKey(
        Chat, on_delete=models.CASCADE, related_name="messages", db_index=True
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sent_messages",
        db_index=True,
    )

    # Message Relations
    reply_to = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="replies"
    )
    forward_from = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="forwards",
    )
    forward_from_chat = models.ForeignKey(
        Chat,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="forwarded_messages",
    )
    forward_from_message_id = models.UUIDField(null=True, blank=True)

    # Content
    type = models.CharField(
        max_length=20, choices=MessageType.choices, default=MessageType.TEXT
    )
    content = models.TextField(blank=True)
    content_encrypted = EncryptedTextField(blank=True)  # For secret chats

    # Status and Metadata
    status = models.CharField(
        max_length=20, choices=MessageStatus.choices, default=MessageStatus.SENDING
    )
    delete_type = models.CharField(
        max_length=20, choices=DeleteType.choices, null=True, blank=True
    )
    message_thread_id = models.UUIDField(null=True, blank=True)  # For forum topics

    # Media and Attachments
    has_media = models.BooleanField(default=False, db_index=True)
    media_group_id = models.CharField(
        max_length=64, blank=True, db_index=True
    )  # Group photos/videos

    # Message Features
    is_from_offline = models.BooleanField(default=False)
    is_scheduled = models.BooleanField(default=False)
    is_silent = models.BooleanField(default=False)  # No notification
    is_pinned = models.BooleanField(default=False)
    is_forwarded = models.BooleanField(default=False)

    # Editing and History
    edit_date = models.DateTimeField(null=True, blank=True)
    edit_hide = models.BooleanField(default=False)
    original_content = models.TextField(blank=True)  # Store original before editing
    edit_count = models.PositiveIntegerField(default=0)

    # Reactions and Interactions
    reactions = models.JSONField(
        default=dict, blank=True
    )  # {"👍": [user_ids], "❤️": [user_ids]}
    mentions = models.JSONField(
        default=list, blank=True
    )  # [{"user_id": "123", "username": "user"}]
    read_by = models.ManyToManyField(
        User, blank=True, related_name="read_messages"
    )  # Users who have read this message
    views_count = models.PositiveIntegerField(default=0)
    forwards_count = models.PositiveIntegerField(default=0)
    replies_count = models.PositiveIntegerField(default=0)

    # Advanced Features
    auto_delete_date = models.DateTimeField(null=True, blank=True)
    ttl_seconds = models.PositiveIntegerField(null=True, blank=True)  # Time to live

    # Scheduling
    scheduled_date = models.DateTimeField(null=True, blank=True, db_index=True)

    # Special Message Data
    poll_data = models.JSONField(default=dict, blank=True)
    game_data = models.JSONField(default=dict, blank=True)
    payment_data = models.JSONField(default=dict, blank=True)
    location_data = models.JSONField(default=dict, blank=True)
    contact_data = models.JSONField(default=dict, blank=True)
    venue_data = models.JSONField(default=dict, blank=True)
    call_data = models.JSONField(default=dict, blank=True)

    # System Message Data
    action = models.CharField(max_length=50, blank=True)  # For system messages
    action_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="system_message_actions",
    )

    # AI and Bot Features
    via_bot = models.ForeignKey(
        "ChatBot",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bot_messages",
    )
    inline_keyboard = models.JSONField(default=list, blank=True)  # Bot inline keyboards

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = ChatMessageQuerySet.as_manager()

    class Meta:
        verbose_name = _("Chat Message")
        verbose_name_plural = _("Chat Messages")
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["chat", "created_at"]),
            models.Index(fields=["sender", "created_at"]),
            models.Index(fields=["type", "has_media"]),
            models.Index(fields=["is_scheduled", "scheduled_date"]),
            models.Index(fields=["media_group_id"]),
            models.Index(fields=["message_thread_id"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"Message from {self.sender.username} in {self.chat.name}"

    def add_reaction(self, user, emoji):
        """Add or toggle reaction."""
        user_id = str(user.id)
        if emoji not in self.reactions:
            self.reactions[emoji] = []

        if user_id in self.reactions[emoji]:
            self.reactions[emoji].remove(user_id)
            if not self.reactions[emoji]:
                del self.reactions[emoji]
        else:
            self.reactions[emoji].append(user_id)

        self.save(update_fields=["reactions"])

    def get_reactions_summary(self):
        """Get reactions count summary."""
        return {emoji: len(users) for emoji, users in self.reactions.items()}

    def mark_as_read(self, user):
        """Mark message as read by user."""
        self.read_by.add(user)
        participant = ChatParticipant.objects.filter(user=user, chat=self.chat).first()
        if participant:
            participant.update_last_read(self.id)

    def soft_delete(self, delete_type=DeleteType.FOR_ME, user=None):
        """Soft delete message."""
        self.status = self.MessageStatus.DELETED
        self.delete_type = delete_type
        self.deleted_at = timezone.now()

        if delete_type == self.DeleteType.FOR_EVERYONE:
            self.content = _("This message was deleted")

        self.save(update_fields=["status", "delete_type", "deleted_at", "content"])

    def can_be_edited(self, user):
        """Check if message can be edited by user."""
        if self.sender != user:
            return False

        if self.type not in [
            self.MessageType.TEXT,
            self.MessageType.PHOTO,
            self.MessageType.VIDEO,
            self.MessageType.DOCUMENT,
        ]:
            return False

        # Can edit within 48 hours
        time_limit = timezone.now() - timedelta(hours=48)
        return self.created_at > time_limit

    def can_be_deleted(self, user):
        """Check if message can be deleted by user."""
        if self.sender == user:
            return True

        # Check if user is admin in the chat
        participant = ChatParticipant.objects.filter(user=user, chat=self.chat).first()
        return participant and participant.can_delete_messages

    @property
    def is_media_message(self):
        """Check if message contains media."""
        return self.type in [
            self.MessageType.PHOTO,
            self.MessageType.VIDEO,
            self.MessageType.AUDIO,
            self.MessageType.VOICE,
            self.MessageType.VIDEO_NOTE,
            self.MessageType.DOCUMENT,
            self.MessageType.STICKER,
            self.MessageType.ANIMATION,
        ]

    @property
    def is_service_message(self):
        """Check if message is a service message."""
        return self.type in [self.MessageType.SYSTEM, self.MessageType.SERVICE]

    @property
    def is_reply(self):
        """Check if message is a reply to another message."""
        return self.reply_to_id is not None


class ChatAttachment(models.Model):
    """
    File attachments for messages with comprehensive metadata.
    """

    class AttachmentType(models.TextChoices):
        PHOTO = "photo", _("Photo")
        VIDEO = "video", _("Video")
        AUDIO = "audio", _("Audio")
        VOICE = "voice", _("Voice Note")
        VIDEO_NOTE = "video_note", _("Video Note")
        DOCUMENT = "document", _("Document")
        STICKER = "sticker", _("Sticker")
        ANIMATION = "animation", _("GIF/Animation")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(
        ChatMessage, on_delete=models.CASCADE, related_name="attachments"
    )

    # File Information
    file = models.FileField(upload_to="chat_attachments/")
    file_name = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveBigIntegerField()  # In bytes
    mime_type = models.CharField(max_length=100, blank=True)
    type = models.CharField(max_length=20, choices=AttachmentType.choices)

    # Media Metadata
    thumbnail = models.ImageField(upload_to="chat_thumbnails/", blank=True, null=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    duration = models.PositiveIntegerField(
        null=True, blank=True
    )  # For audio/video in seconds

    # Additional Data
    caption = models.TextField(blank=True, max_length=1024)
    title = models.CharField(max_length=255, blank=True)
    performer = models.CharField(max_length=255, blank=True)  # For audio

    # Security
    is_encrypted = models.BooleanField(default=False)
    checksum = models.CharField(max_length=64, blank=True)  # SHA-256 hash
    download_count = models.PositiveIntegerField(default=0)

    # Processing Status
    is_processing = models.BooleanField(default=False)
    processing_error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Chat Attachment")
        verbose_name_plural = _("Chat Attachments")
        indexes = [
            models.Index(fields=["message", "type"]),
            models.Index(fields=["file_size"]),
        ]

    def __str__(self):
        return f"{self.get_type_display()} attachment: {self.file_name or 'Unnamed'}"

    def save(self, *args, **kwargs):
        if self.file and not self.file_size:
            self.file_size = self.file.size

        # Sanitize file name to prevent path traversal
        if self.file and hasattr(self.file, "name") and self.file.name:
            import os

            from django.utils.text import get_valid_filename

            # Get just the filename without path components
            safe_filename = os.path.basename(self.file.name)

            # Remove any remaining path traversal attempts
            safe_filename = (
                safe_filename.replace("..", "").replace("/", "").replace("\\", "")
            )

            # Make sure filename is valid
            safe_filename = get_valid_filename(safe_filename)

            # Set the sanitized filename
            if safe_filename:
                self.file.name = safe_filename
            else:
                # Fallback to a default name if sanitization removes everything
                import uuid

                ext = (
                    os.path.splitext(self.file.name)[1] if "." in self.file.name else ""
                )
                self.file.name = f"attachment_{uuid.uuid4().hex[:8]}{ext}"

        super().save(*args, **kwargs)


class ChatFolder(models.Model):
    """
    User-defined chat folders for organization.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="chat_folders"
    )
    name = models.CharField(max_length=50)
    emoji = models.CharField(max_length=10, blank=True)
    chats = models.ManyToManyField(Chat, blank=True)

    # Filter Settings
    include_private = models.BooleanField(default=True)
    include_groups = models.BooleanField(default=True)
    include_channels = models.BooleanField(default=True)
    include_bots = models.BooleanField(default=True)
    include_muted = models.BooleanField(default=True)
    include_read = models.BooleanField(default=True)
    include_archived = models.BooleanField(default=False)

    # Advanced Filters
    contacts = models.ManyToManyField(User, blank=True, related_name="folder_contacts")
    exclude_contacts = models.ManyToManyField(
        User, blank=True, related_name="folder_exclude_contacts"
    )

    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Chat Folder")
        verbose_name_plural = _("Chat Folders")
        unique_together = [["user", "name"]]
        ordering = ["order", "name"]

    def __str__(self):
        return f"{self.emoji} {self.name}"

    def get_chats_queryset(self):
        """Get chats that match this folder's criteria."""
        # Start with manually added chats for this folder
        queryset = self.chats.all()

        # Apply type filters
        chat_types = []
        if self.include_private:
            chat_types.extend([Chat.ChatType.PRIVATE, Chat.ChatType.SECRET])
        if self.include_groups:
            chat_types.extend(
                [Chat.ChatType.GROUP, Chat.ChatType.SUPERGROUP, Chat.ChatType.FORUM]
            )
        if self.include_channels:
            chat_types.append(Chat.ChatType.CHANNEL)
        if self.include_bots:
            chat_types.append(Chat.ChatType.BOT)

        if chat_types:
            queryset = queryset.filter(type__in=chat_types)

        # Apply status filters
        if not self.include_archived:
            queryset = queryset.exclude(status=Chat.ChatStatus.ARCHIVED)

        # Apply contact filters
        if self.contacts.exists():
            queryset = queryset.filter(participants__in=self.contacts.all())
        if self.exclude_contacts.exists():
            queryset = queryset.exclude(participants__in=self.exclude_contacts.all())

        return queryset.distinct()


class ChatBot(models.Model):
    """
    Bot entities for automated interactions.
    """

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="bot_profile"
    )

    # Bot Information
    description = models.TextField(blank=True, max_length=512)
    about = models.TextField(blank=True, max_length=120)
    bot_pic = models.ImageField(upload_to="bot_pics/", blank=True, null=True)

    # Authentication
    token = models.CharField(max_length=100, unique=True)
    token_hash = models.CharField(max_length=64)  # SHA256 of token

    # Commands and Features
    commands = models.JSONField(
        default=list, blank=True
    )  # [{"command": "/start", "description": "..."}]
    inline_placeholder = models.CharField(max_length=64, blank=True)  # For inline bots

    # Capabilities
    is_inline = models.BooleanField(default=False)
    can_join_groups = models.BooleanField(default=True)
    can_read_all_group_messages = models.BooleanField(default=False)
    supports_inline_queries = models.BooleanField(default=False)

    # Integration
    webhook_url = models.URLField(blank=True)
    webhook_secret = models.CharField(max_length=100, blank=True)

    # Statistics
    messages_sent = models.PositiveIntegerField(default=0)
    users_count = models.PositiveIntegerField(default=0)

    # Settings
    is_verified = models.BooleanField(default=False)
    is_premium = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Chat Bot")
        verbose_name_plural = _("Chat Bots")

    def __str__(self):
        return f"Bot: {self.user.username}"

    def generate_token(self):
        """Generate a new bot token."""
        import hashlib
        import secrets

        self.token = f"{self.id}:{secrets.token_urlsafe(32)}"
        self.token_hash = hashlib.sha256(self.token.encode()).hexdigest()
        self.save(update_fields=["token", "token_hash"])
        return self.token


class ChatCall(models.Model):
    """
    Voice and video call management.
    """

    class CallType(models.TextChoices):
        VOICE = "voice", _("Voice Call")
        VIDEO = "video", _("Video Call")
        GROUP_VOICE = "group_voice", _("Group Voice Call")
        GROUP_VIDEO = "group_video", _("Group Video Call")
        LIVE_STREAM = "live_stream", _("Live Stream")

    class CallStatus(models.TextChoices):
        RINGING = "ringing", _("Ringing")
        ONGOING = "ongoing", _("Ongoing")
        ACTIVE = "active", _("Active")
        ENDED = "ended", _("Ended")
        MISSED = "missed", _("Missed")
        DECLINED = "declined", _("Declined")
        FAILED = "failed", _("Failed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="calls")
    initiator = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="initiated_calls"
    )

    # Call Details
    type = models.CharField(
        max_length=20, choices=CallType.choices, default=CallType.VOICE
    )
    status = models.CharField(
        max_length=20, choices=CallStatus.choices, default=CallStatus.RINGING
    )

    # Participants
    participants = models.ManyToManyField(
        User, through="ChatCallParticipant", related_name="calls"
    )
    max_participants = models.PositiveIntegerField(default=30)

    # Timing
    start_time = models.DateTimeField(auto_now_add=True)
    answer_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    duration = models.PositiveIntegerField(default=0)  # In seconds

    # Quality and Technical
    quality_rating = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1.0), MaxValueValidator(5.0)],
    )
    connection_data = models.JSONField(
        default=dict, blank=True
    )  # WebRTC connection info

    # Recording
    is_recorded = models.BooleanField(default=False)
    recording_file = models.FileField(
        upload_to="call_recordings/", blank=True, null=True
    )

    # Settings
    is_video_disabled = models.BooleanField(default=False)
    is_screen_sharing = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Chat Call")
        verbose_name_plural = _("Chat Calls")
        ordering = ["-start_time"]
        indexes = [
            models.Index(fields=["chat", "start_time"]),
            models.Index(fields=["status", "type"]),
        ]

    def __str__(self):
        return f"{self.get_type_display()} in {self.chat} ({self.get_status_display()})"

    def end_call(self):
        """End the call and calculate duration."""
        if self.status == self.CallStatus.ONGOING:
            self.end_time = timezone.now()
            self.status = self.CallStatus.ENDED
            if self.answer_time:
                self.duration = int((self.end_time - self.answer_time).total_seconds())
            self.save(update_fields=["end_time", "status", "duration"])

    def get_duration_display(self):
        """Get human-readable duration."""
        if self.duration:
            minutes, seconds = divmod(self.duration, 60)
            hours, minutes = divmod(minutes, 60)
            if hours:
                return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            return f"{minutes:02d}:{seconds:02d}"
        return "00:00"


class ChatCallParticipant(models.Model):
    """
    Call participant details.
    """

    class ParticipantStatus(models.TextChoices):
        INVITED = "invited", _("Invited")
        RINGING = "ringing", _("Ringing")
        JOINED = "joined", _("Joined")
        LEFT = "left", _("Left")
        DECLINED = "declined", _("Declined")
        MISSED = "missed", _("Missed")

    call = models.ForeignKey(ChatCall, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=20,
        choices=ParticipantStatus.choices,
        default=ParticipantStatus.INVITED,
    )

    # Timing
    invited_at = models.DateTimeField(auto_now_add=True)
    joined_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)

    # Audio/Video Status
    is_muted = models.BooleanField(default=False)
    is_video_enabled = models.BooleanField(default=True)
    is_screen_sharing = models.BooleanField(default=False)

    # Technical
    connection_quality = models.IntegerField(
        default=5, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )

    class Meta:
        verbose_name = _("Call Participant")
        verbose_name_plural = _("Call Participants")
        unique_together = [["call", "user"]]

    def __str__(self):
        return f"{self.user.username} in {self.call}"


class ChatPoll(models.Model):
    """
    Polls and quizzes in chats.
    """

    class PollType(models.TextChoices):
        REGULAR = "regular", _("Regular Poll")
        QUIZ = "quiz", _("Quiz")

    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="polls")
    message = models.OneToOneField(
        ChatMessage,
        on_delete=models.CASCADE,
        related_name="poll",
        null=True,
        blank=True,
    )

    # Poll Details
    question = models.CharField(max_length=300)
    type = models.CharField(
        max_length=20, choices=PollType.choices, default=PollType.REGULAR
    )
    is_anonymous = models.BooleanField(default=True)
    allows_multiple_answers = models.BooleanField(default=False)
    is_closed = models.BooleanField(default=False)

    # Quiz Specific
    correct_option_id = models.PositiveIntegerField(null=True, blank=True)
    explanation = models.TextField(blank=True, max_length=200)

    # Timing
    open_period = models.PositiveIntegerField(null=True, blank=True)  # Seconds
    close_date = models.DateTimeField(null=True, blank=True)

    # Statistics
    total_voter_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Chat Poll")
        verbose_name_plural = _("Chat Polls")

    def __str__(self):
        return f"Poll: {self.question[:50]}..."

    def close_poll(self):
        """Close the poll."""
        self.is_closed = True
        self.save(update_fields=["is_closed"])

    def get_results(self):
        """Get poll results."""
        return self.options.annotate(vote_count=Count("votes")).order_by("-vote_count")


class ChatPollOption(models.Model):
    """
    Poll options.
    """

    poll = models.ForeignKey(ChatPoll, on_delete=models.CASCADE, related_name="options")
    text = models.CharField(max_length=100)
    voter_count = models.PositiveIntegerField(default=0)
    order = models.PositiveIntegerField()

    class Meta:
        verbose_name = _("Poll Option")
        verbose_name_plural = _("Poll Options")
        ordering = ["order"]
        unique_together = [["poll", "order"]]

    def __str__(self):
        return f"{self.poll.question}: {self.text}"


class ChatPollAnswer(models.Model):
    """
    User votes in polls.
    """

    poll = models.ForeignKey(ChatPoll, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    option_ids = models.JSONField(default=list)  # For multiple choice

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Poll Answer")
        verbose_name_plural = _("Poll Answers")
        unique_together = [["poll", "user"]]

    def __str__(self):
        return f"{self.user.username}'s vote in {self.poll.question[:30]}..."


class ChatStickerSet(models.Model):
    """
    Sticker sets for enhanced messaging.
    """

    class StickerType(models.TextChoices):
        STATIC = "static", _("Static")
        ANIMATED = "animated", _("Animated")
        VIDEO = "video", _("Video")

    name = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=64)
    type = models.CharField(
        max_length=20, choices=StickerType.choices, default=StickerType.STATIC
    )

    creator = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="created_sticker_sets"
    )
    thumb = models.ImageField(upload_to="sticker_thumbs/", blank=True, null=True)

    # Settings
    is_official = models.BooleanField(default=False)
    is_masks = models.BooleanField(default=False)
    is_premium = models.BooleanField(default=False)

    # Statistics
    install_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Sticker Set")
        verbose_name_plural = _("Sticker Sets")

    def __str__(self):
        return self.title

    def get_stickers_count(self):
        return self.stickers.count()


class ChatSticker(models.Model):
    """
    Individual stickers.
    """

    sticker_set = models.ForeignKey(
        ChatStickerSet, on_delete=models.CASCADE, related_name="stickers"
    )

    # File Data
    file = models.FileField(upload_to="stickers/")
    thumb = models.ImageField(upload_to="sticker_thumbs/", blank=True, null=True)
    emoji = models.CharField(max_length=20, blank=True)

    # Dimensions
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    file_size = models.PositiveIntegerField()

    # Mask Position (for mask stickers)
    mask_position = models.JSONField(default=dict, blank=True)

    # Premium
    is_premium = models.BooleanField(default=False)

    order = models.PositiveIntegerField()

    class Meta:
        verbose_name = _("Sticker")
        verbose_name_plural = _("Stickers")
        ordering = ["order"]
        unique_together = [["sticker_set", "order"]]

    def __str__(self):
        return f"{self.sticker_set.title} - {self.emoji}"


class UserStickerSet(models.Model):
    """
    User's installed sticker sets.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="installed_sticker_sets"
    )
    sticker_set = models.ForeignKey(ChatStickerSet, on_delete=models.CASCADE)
    order = models.PositiveIntegerField()

    installed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("User Sticker Set")
        verbose_name_plural = _("User Sticker Sets")
        unique_together = [["user", "sticker_set"]]
        ordering = ["order"]

    def __str__(self):
        return f"{self.user.username} - {self.sticker_set.title}"


class ChatTheme(models.Model):
    """
    Chat themes for customization.
    """

    name = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=100)

    # Colors
    accent_color = models.CharField(max_length=7)  # Hex color
    background_color = models.CharField(max_length=7, blank=True)
    text_color = models.CharField(max_length=7, blank=True)

    # Files
    background_image = models.ImageField(
        upload_to="chat_themes/", blank=True, null=True
    )
    pattern_image = models.ImageField(upload_to="chat_patterns/", blank=True, null=True)

    # Settings
    is_dark = models.BooleanField(default=False)
    is_premium = models.BooleanField(default=False)
    is_default = models.BooleanField(default=False)

    # Additional styling
    settings = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Chat Theme")
        verbose_name_plural = _("Chat Themes")

    def __str__(self):
        return self.title


class ChatModerationLog(models.Model):
    """
    Moderation actions log for groups and channels.
    """

    class ActionType(models.TextChoices):
        # User Actions
        BAN_USER = "ban_user", _("Ban User")
        UNBAN_USER = "unban_user", _("Unban User")
        RESTRICT_USER = "restrict_user", _("Restrict User")
        UNRESTRICT_USER = "unrestrict_user", _("Unrestrict User")
        PROMOTE_USER = "promote_user", _("Promote User")
        DEMOTE_USER = "demote_user", _("Demote User")

        # Message Actions
        DELETE_MESSAGE = "delete_message", _("Delete Message")
        PIN_MESSAGE = "pin_message", _("Pin Message")
        UNPIN_MESSAGE = "unpin_message", _("Unpin Message")

        # Chat Actions
        CHANGE_TITLE = "change_title", _("Change Title")
        CHANGE_DESCRIPTION = "change_description", _("Change Description")
        CHANGE_PHOTO = "change_photo", _("Change Photo")
        CHANGE_PERMISSIONS = "change_permissions", _("Change Permissions")

        # Other
        INVITE_USERS = "invite_users", _("Invite Users")
        CREATE_INVITE_LINK = "create_invite_link", _("Create Invite Link")
        REVOKE_INVITE_LINK = "revoke_invite_link", _("Revoke Invite Link")

    chat = models.ForeignKey(
        Chat, on_delete=models.CASCADE, related_name="moderation_logs"
    )
    moderator = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="moderation_actions"
    )

    # Action Details
    action = models.CharField(max_length=30, choices=ActionType.choices)
    target_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderation_targets",
    )
    target_message = models.ForeignKey(
        ChatMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderation_actions",
    )

    # Additional Data
    reason = models.TextField(blank=True, max_length=200)
    duration = models.DurationField(null=True, blank=True)  # For temporary restrictions
    old_value = models.TextField(blank=True)  # Store old values for changes
    new_value = models.TextField(blank=True)  # Store new values for changes

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Moderation Log")
        verbose_name_plural = _("Moderation Logs")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["chat", "created_at"]),
            models.Index(fields=["moderator", "action"]),
            models.Index(fields=["target_user"]),
        ]

    def __str__(self):
        return f"{self.get_action_display()} in {self.chat} by {self.moderator}"


class ChatInviteLink(models.Model):
    """
    Invite links for chats.
    """

    chat = models.ForeignKey(
        Chat, on_delete=models.CASCADE, related_name="invite_links"
    )
    creator = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="created_invite_links"
    )

    # Link Details
    link = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=32, blank=True)

    # Settings
    expire_date = models.DateTimeField(null=True, blank=True)
    member_limit = models.PositiveIntegerField(null=True, blank=True)
    creates_join_request = models.BooleanField(default=False)

    # Status
    is_primary = models.BooleanField(default=False)
    is_revoked = models.BooleanField(default=False)

    # Statistics
    usage_count = models.PositiveIntegerField(default=0)
    pending_join_request_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Invite Link")
        verbose_name_plural = _("Invite Links")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invite link for {self.chat}: {self.link}"

    def is_valid(self):
        """Check if invite link is still valid."""
        if self.is_revoked:
            return False

        if self.expire_date and timezone.now() > self.expire_date:
            return False

        if self.member_limit and self.usage_count >= self.member_limit:
            return False

        return True

    def save(self, *args, **kwargs):
        if not self.link:
            import secrets
            import string
            import time

            # Generate unique link
            attempts = 0
            while True:
                # Add timestamp to reduce collision chance
                timestamp = str(int(time.time()))[-4:]
                random_part = "".join(
                    secrets.choice(string.ascii_letters + string.digits)
                    for _ in range(12)
                )
                self.link = timestamp + random_part

                if not ChatInviteLink.objects.filter(link=self.link).exists():
                    break

                attempts += 1
                if attempts > 10:
                    # Fallback to UUID if too many collisions
                    import uuid

                    self.link = uuid.uuid4().hex[:16]
                    break

        super().save(*args, **kwargs)

    def revoke(self):
        """Revoke the invite link."""
        self.is_revoked = True
        self.revoked_at = timezone.now()
        self.save(update_fields=["is_revoked", "revoked_at"])


class ChatJoinRequest(models.Model):
    """
    Join requests for private groups/channels.
    """

    class RequestStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        DECLINED = "declined", _("Declined")

    chat = models.ForeignKey(
        Chat, on_delete=models.CASCADE, related_name="join_requests"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="chat_join_requests"
    )
    invite_link = models.ForeignKey(
        ChatInviteLink,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="join_requests",
    )

    status = models.CharField(
        max_length=20, choices=RequestStatus.choices, default=RequestStatus.PENDING
    )
    bio = models.TextField(blank=True, max_length=70)  # User's bio for request

    # Decision
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_join_requests",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Join Request")
        verbose_name_plural = _("Join Requests")
        unique_together = [["chat", "user"]]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} -> {self.chat}"

    def approve(self, approved_by_user):
        """Approve the join request."""
        self.status = self.RequestStatus.APPROVED
        self.approved_by = approved_by_user
        self.decided_at = timezone.now()
        self.save(update_fields=["status", "approved_by", "decided_at"])

        # Add user to chat
        ChatParticipant.objects.create(
            user=self.user, chat=self.chat, role=ChatParticipant.ParticipantRole.MEMBER
        )

    def decline(self):
        """Decline the join request."""
        self.status = self.RequestStatus.DECLINED
        self.decided_at = timezone.now()
        self.save(update_fields=["status", "decided_at"])


# Performance and caching utilities
class ChatCache:
    """Utility class for chat-related caching."""

    @staticmethod
    def get_unread_count(user_id, chat_id):
        """Get cached unread count for user in chat."""
        cache_key = f"unread_count_{user_id}_{chat_id}"
        return cache.get(cache_key)

    @staticmethod
    def set_unread_count(user_id, chat_id, count):
        """Set cached unread count for user in chat."""
        cache_key = f"unread_count_{user_id}_{chat_id}"
        cache.set(cache_key, count, 3600)  # 1 hour

    @staticmethod
    def invalidate_unread_count(user_id, chat_id):
        """Invalidate cached unread count."""
        cache_key = f"unread_count_{user_id}_{chat_id}"
        cache.delete(cache_key)

    @staticmethod
    def get_online_users(chat_id):
        """Get cached online users for chat."""
        cache_key = f"online_users_{chat_id}"
        return cache.get(cache_key, [])

    @staticmethod
    def add_online_user(chat_id, user_id):
        """Add user to online users cache."""
        cache_key = f"online_users_{chat_id}"
        online_users = cache.get(cache_key, [])
        if user_id not in online_users:
            online_users.append(user_id)
            cache.set(cache_key, online_users, 300)  # 5 minutes

    @staticmethod
    def remove_online_user(chat_id, user_id):
        """Remove user from online users cache."""
        cache_key = f"online_users_{chat_id}"
        online_users = cache.get(cache_key, [])
        if user_id in online_users:
            online_users.remove(user_id)
            cache.set(cache_key, online_users, 300)


class ChatWebhook(models.Model):
    """
    Webhook configuration for chat events.
    """

    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="webhooks")
    url = models.URLField(max_length=512)
    events = models.JSONField(default=list)  # List of event types to send
    secret = models.CharField(max_length=256, blank=True)
    is_active = models.BooleanField(default=True)

    # Statistics
    last_delivery = models.DateTimeField(null=True, blank=True)
    delivery_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Chat Webhook")
        verbose_name_plural = _("Chat Webhooks")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Webhook for {self.chat} -> {self.url}"
