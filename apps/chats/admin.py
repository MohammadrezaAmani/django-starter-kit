from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db.models import Count
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

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
    ChatPollOption,
    ChatSticker,
    ChatStickerSet,
    ChatTheme,
    UserStickerSet,
)


class ChatTypeFilter(SimpleListFilter):
    """Filter chats by type."""

    title = _("Chat Type")
    parameter_name = "type"

    def lookups(self, request, model_admin):
        return Chat.ChatType.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(type=self.value())
        return queryset


class ChatStatusFilter(SimpleListFilter):
    """Filter chats by status."""

    title = _("Status")
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return Chat.ChatStatus.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(status=self.value())
        return queryset


class HasLinkedProjectFilter(SimpleListFilter):
    """Filter chats that have linked projects."""

    title = _("Linked to Project")
    parameter_name = "has_project"

    def lookups(self, request, model_admin):
        return (
            ("yes", _("Yes")),
            ("no", _("No")),
        )

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(linked_project__isnull=False)
        elif self.value() == "no":
            return queryset.filter(linked_project__isnull=True)
        return queryset


class ParticipantInline(admin.TabularInline):
    """Inline for chat participants."""

    model = ChatParticipant
    extra = 0
    readonly_fields = ("joined_at", "last_read_at", "unread_count", "last_activity_at")
    fields = (
        "user",
        "role",
        "status",
        "custom_title",
        "can_send_messages",
        "can_send_media",
        "can_delete_messages",
        "can_ban_users",
        "notification_level",
        "folder",
        "joined_at",
        "unread_count",
    )
    autocomplete_fields = ["user"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")


class ChatMessageInline(admin.TabularInline):
    """Inline for recent chat messages."""

    model = ChatMessage
    fk_name = "chat"
    extra = 0
    readonly_fields = (
        "id",
        "sender",
        "type",
        "content_preview",
        "created_at",
        "status",
    )
    fields = ("id", "sender", "type", "content_preview", "status", "created_at")
    ordering = ("-created_at",)
    max_num = 10
    show_change_link = True

    def content_preview(self, obj):
        """Show content preview."""
        if obj.content:
            return obj.content[:100] + ("..." if len(obj.content) > 100 else "")
        return f"[{obj.get_type_display()}]"

    content_preview.short_description = _("Content Preview")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("sender")
            .order_by("-created_at")
        )


@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    """Admin interface for Chat model."""

    list_display = (
        "name_or_id",
        "type",
        "status",
        "participants_count_display",
        "messages_count",
        "creator",
        "is_encrypted",
        "created_at",
    )
    list_filter = (
        ChatTypeFilter,
        ChatStatusFilter,
        HasLinkedProjectFilter,
        "is_encrypted",
        "is_public",
        "is_verified",
        "created_at",
    )
    search_fields = (
        "name",
        "description",
        "username",
        "creator__username",
        "creator__email",
    )
    readonly_fields = (
        "id",
        "participants_count",
        "messages_count",
        "online_count",
        "created_at",
        "updated_at",
        "invite_link_display",
    )
    autocomplete_fields = ["creator", "linked_project", "linked_task", "linked_network"]
    inlines = [ParticipantInline, ChatMessageInline]

    fieldsets = (
        (
            _("Basic Information"),
            {
                "fields": (
                    "id",
                    "type",
                    "name",
                    "username",
                    "description",
                    "about",
                    "photo",
                    "photo_small",
                    "status",
                )
            },
        ),
        (
            _("Settings"),
            {
                "fields": (
                    "is_public",
                    "is_verified",
                    "is_scam",
                    "is_fake",
                    "max_members",
                    "slow_mode_delay",
                    "has_protected_content",
                    "has_aggressive_anti_spam_enabled",
                    "auto_delete_timer",
                )
            },
        ),
        (_("Security"), {"fields": ("is_encrypted", "encryption_key_fingerprint")}),
        (
            _("Features"),
            {
                "fields": (
                    "ai_enabled",
                    "has_calls_enabled",
                    "has_video_calls_enabled",
                    "has_group_calls_enabled",
                    "bot_commands",
                )
            },
        ),
        (
            _("Integrations"),
            {"fields": ("linked_project", "linked_task", "linked_network")},
        ),
        (_("Management"), {"fields": ("creator", "last_message", "pinned_message")}),
        (
            _("Statistics"),
            {
                "fields": (
                    "participants_count",
                    "messages_count",
                    "online_count",
                    "created_at",
                    "updated_at",
                )
            },
        ),
        (
            _("Invite"),
            {
                "fields": ("invite_link_display",),
                "classes": ("collapse",),
            },
        ),
        (_("Theming"), {"fields": ("theme", "wallpaper"), "classes": ("collapse",)}),
    )

    def name_or_id(self, obj):
        """Display name or ID."""
        return obj.name or str(obj.id)[:8]

    name_or_id.short_description = _("Name/ID")
    name_or_id.admin_order_field = "name"

    def participants_count_display(self, obj):
        """Display participants count with link."""
        count = obj.participants_count or obj.participants.count()
        url = reverse("admin:chats_chatparticipant_changelist")
        return format_html('<a href="{}?chat__id__exact={}">{}</a>', url, obj.id, count)

    participants_count_display.short_description = _("Participants")

    def invite_link_display(self, obj):
        """Display invite link."""
        if obj.invite_link:
            return format_html(
                '<a href="#" onclick="navigator.clipboard.writeText(\'{}\')">{}</a>',
                obj.invite_link,
                obj.invite_link[:20] + "...",
            )
        return _("Not generated")

    invite_link_display.short_description = _("Invite Link")

    def generate_invite_button(self, obj):
        """Button to generate invite link."""
        if obj.pk:
            return format_html(
                '<a class="button" href="#" onclick="generateInviteLink(\'{}\')">Generate Invite Link</a>',
                obj.pk,
            )
        return _("Save chat first")

    generate_invite_button.short_description = _("Actions")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("creator", "last_message")
            .annotate(participants_count_annotated=Count("participants"))
        )

    class Media:
        js = ("admin/js/chat_admin.js",)
        css = {"all": ("admin/css/chat_admin.css",)}


class MessageTypeFilter(SimpleListFilter):
    """Filter messages by type."""

    title = _("Message Type")
    parameter_name = "type"

    def lookups(self, request, model_admin):
        return ChatMessage.MessageType.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(type=self.value())
        return queryset


class MessageStatusFilter(SimpleListFilter):
    """Filter messages by status."""

    title = _("Status")
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return ChatMessage.MessageStatus.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(status=self.value())
        return queryset


class AttachmentInline(admin.TabularInline):
    """Inline for message attachments."""

    model = ChatAttachment
    extra = 0
    readonly_fields = ("id", "file_size", "created_at", "file_preview")
    fields = ("file", "file_preview", "type", "file_size", "caption")

    def file_preview(self, obj):
        """Show file preview."""
        if obj.file:
            if obj.type in ["photo", "image"]:
                return format_html(
                    '<img src="{}" style="max-width: 100px; max-height: 100px;">',
                    obj.file.url,
                )
            return format_html(
                '<a href="{}" target="_blank">{}</a>', obj.file.url, obj.file.name
            )
        return _("No file")

    file_preview.short_description = _("Preview")


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    """Admin interface for ChatMessage model."""

    list_display = (
        "id_short",
        "chat_link",
        "sender",
        "type",
        "content_preview",
        "status",
        "has_media",
        "reactions_count",
        "created_at",
    )
    list_filter = (
        MessageTypeFilter,
        MessageStatusFilter,
        "has_media",
        "is_forwarded",
        "is_pinned",
        "created_at",
    )
    search_fields = ("content", "sender__username", "chat__name")
    readonly_fields = (
        "id",
        "views_count",
        "forwards_count",
        "replies_count",
        "created_at",
        "updated_at",
        "reactions_display",
    )
    autocomplete_fields = ["chat", "sender", "reply_to", "forward_from", "via_bot"]
    inlines = [AttachmentInline]

    fieldsets = (
        (
            _("Basic Information"),
            {"fields": ("id", "chat", "sender", "type", "status")},
        ),
        (_("Content"), {"fields": ("content", "content_encrypted")}),
        (
            _("Relations"),
            {
                "fields": ("reply_to", "forward_from", "forward_from_chat", "via_bot"),
                "classes": ("collapse",),
            },
        ),
        (
            _("Features"),
            {
                "fields": (
                    "has_media",
                    "is_forwarded",
                    "is_pinned",
                    "is_silent",
                    "is_scheduled",
                    "scheduled_date",
                )
            },
        ),
        (
            _("Editing"),
            {
                "fields": ("edit_date", "edit_count", "original_content"),
                "classes": ("collapse",),
            },
        ),
        (
            _("Statistics"),
            {
                "fields": (
                    "views_count",
                    "forwards_count",
                    "replies_count",
                    "reactions_display",
                    "created_at",
                    "updated_at",
                )
            },
        ),
        (
            _("Special Data"),
            {
                "fields": (
                    "poll_data",
                    "game_data",
                    "payment_data",
                    "location_data",
                    "contact_data",
                    "call_data",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Auto-Delete"),
            {"fields": ("ttl_seconds", "auto_delete_date"), "classes": ("collapse",)},
        ),
    )

    def id_short(self, obj):
        """Short ID display."""
        return str(obj.id)[:8]

    id_short.short_description = _("ID")

    def chat_link(self, obj):
        """Link to chat admin."""
        url = reverse("admin:chats_chat_change", args=[obj.chat.id])
        return format_html(
            '<a href="{}">{}</a>', url, obj.chat.name or str(obj.chat.id)[:8]
        )

    chat_link.short_description = _("Chat")

    def content_preview(self, obj):
        """Content preview."""
        if obj.content:
            return obj.content[:50] + ("..." if len(obj.content) > 50 else "")
        return f"[{obj.get_type_display()}]"

    content_preview.short_description = _("Content")

    def reactions_count(self, obj):
        """Reactions count."""
        return (
            sum(len(users) for users in obj.reactions.values()) if obj.reactions else 0
        )

    reactions_count.short_description = _("Reactions")

    def reactions_display(self, obj):
        """Display reactions nicely."""
        if not obj.reactions:
            return _("No reactions")

        reactions_html = []
        for emoji, user_ids in obj.reactions.items():
            reactions_html.append(f"{emoji} {len(user_ids)}")

        return format_html(" | ".join(reactions_html))

    reactions_display.short_description = _("Reactions")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("chat", "sender")


@admin.register(ChatParticipant)
class ChatParticipantAdmin(admin.ModelAdmin):
    """Admin interface for ChatParticipant model."""

    list_display = (
        "user",
        "chat_link",
        "role",
        "status",
        "custom_title",
        "unread_count",
        "joined_at",
        "last_activity_at",
    )
    list_filter = (
        "role",
        "status",
        "notification_level",
        "can_send_messages",
        "can_delete_messages",
        "joined_at",
    )
    search_fields = ("user__username", "user__email", "chat__name", "custom_title")
    readonly_fields = (
        "joined_at",
        "last_read_at",
        "last_activity_at",
        "unread_count",
        "unread_mentions_count",
    )
    autocomplete_fields = ["user", "chat"]

    fieldsets = (
        (
            _("Basic Information"),
            {"fields": ("user", "chat", "role", "status", "custom_title")},
        ),
        (
            _("Permissions"),
            {
                "fields": (
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
                )
            },
        ),
        (_("Preferences"), {"fields": ("notification_level", "muted_until", "folder")}),
        (
            _("Activity"),
            {
                "fields": (
                    "joined_at",
                    "last_read_at",
                    "last_activity_at",
                    "unread_count",
                    "unread_mentions_count",
                )
            },
        ),
        (
            _("Restrictions"),
            {
                "fields": ("banned_until", "restricted_until", "ban_reason"),
                "classes": ("collapse",),
            },
        ),
    )

    def chat_link(self, obj):
        """Link to chat admin."""
        url = reverse("admin:chats_chat_change", args=[obj.chat.id])
        return format_html(
            '<a href="{}">{}</a>', url, obj.chat.name or str(obj.chat.id)[:8]
        )

    chat_link.short_description = _("Chat")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "chat")


@admin.register(ChatAttachment)
class ChatAttachmentAdmin(admin.ModelAdmin):
    """Admin interface for ChatAttachment model."""

    list_display = (
        "id_short",
        "message_link",
        "type",
        "file_name",
        "file_size_display",
        "created_at",
    )
    list_filter = ("type", "is_encrypted", "created_at")
    search_fields = ("file_name", "caption", "message__content")
    readonly_fields = ("id", "file_size", "created_at", "file_preview")
    autocomplete_fields = ["message"]

    def id_short(self, obj):
        """Short ID display."""
        return str(obj.id)[:8]

    id_short.short_description = _("ID")

    def message_link(self, obj):
        """Link to message admin."""
        url = reverse("admin:chats_chatmessage_change", args=[obj.message.id])
        return format_html('<a href="{}">{}</a>', url, str(obj.message.id)[:8])

    message_link.short_description = _("Message")

    def file_size_display(self, obj):
        """Human readable file size."""
        size = obj.file_size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    file_size_display.short_description = _("Size")

    def file_preview(self, obj):
        """File preview."""
        if obj.file:
            if obj.type in ["photo", "image"]:
                return format_html(
                    '<img src="{}" style="max-width: 200px; max-height: 200px;">',
                    obj.file.url,
                )
            return format_html(
                '<a href="{}" target="_blank">Download</a>', obj.file.url
            )
        return _("No file")

    file_preview.short_description = _("Preview")


@admin.register(ChatBot)
class ChatBotAdmin(admin.ModelAdmin):
    """Admin interface for ChatBot model."""

    list_display = (
        "user",
        "description_short",
        "is_inline",
        "can_join_groups",
        "messages_sent",
        "users_count",
        "created_at",
    )
    list_filter = (
        "is_inline",
        "can_join_groups",
        "can_read_all_group_messages",
        "is_verified",
        "is_premium",
        "created_at",
    )
    search_fields = ("user__username", "description", "about")
    readonly_fields = (
        "token_display",
        "token_hash",
        "messages_sent",
        "users_count",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ["user"]

    fieldsets = (
        (
            _("Basic Information"),
            {"fields": ("user", "description", "about", "bot_pic")},
        ),
        (
            _("Authentication"),
            {"fields": ("token_display", "token_hash"), "classes": ("collapse",)},
        ),
        (_("Commands"), {"fields": ("commands", "inline_placeholder")}),
        (
            _("Capabilities"),
            {
                "fields": (
                    "is_inline",
                    "can_join_groups",
                    "can_read_all_group_messages",
                    "supports_inline_queries",
                )
            },
        ),
        (_("Integration"), {"fields": ("webhook_url", "webhook_secret")}),
        (_("Status"), {"fields": ("is_verified", "is_premium")}),
        (
            _("Statistics"),
            {"fields": ("messages_sent", "users_count", "created_at", "updated_at")},
        ),
    )

    def description_short(self, obj):
        """Short description."""
        return obj.description[:50] + ("..." if len(obj.description) > 50 else "")

    description_short.short_description = _("Description")

    def token_display(self, obj):
        """Masked token display."""
        if obj.token:
            return obj.token[:10] + "..." + obj.token[-10:]
        return _("Not set")

    token_display.short_description = _("Token")


@admin.register(ChatCall)
class ChatCallAdmin(admin.ModelAdmin):
    """Admin interface for ChatCall model."""

    list_display = (
        "id_short",
        "chat_link",
        "type",
        "status",
        "initiator",
        "participants_count",
        "duration_display",
        "start_time",
    )
    list_filter = ("type", "status", "is_recorded", "start_time")
    search_fields = ("chat__name", "initiator__username")
    readonly_fields = (
        "id",
        "duration",
        "start_time",
        "answer_time",
        "end_time",
        "participants_count_display",
    )
    autocomplete_fields = ["chat", "initiator"]

    def id_short(self, obj):
        """Short ID display."""
        return str(obj.id)[:8]

    id_short.short_description = _("ID")

    def chat_link(self, obj):
        """Link to chat admin."""
        url = reverse("admin:chats_chat_change", args=[obj.chat.id])
        return format_html(
            '<a href="{}">{}</a>', url, obj.chat.name or str(obj.chat.id)[:8]
        )

    chat_link.short_description = _("Chat")

    def participants_count(self, obj):
        """Participants count."""
        return obj.participants.count()

    participants_count.short_description = _("Participants")

    def participants_count_display(self, obj):
        """Participants count with link."""
        count = obj.participants.count()
        url = reverse("admin:chats_chatcallparticipant_changelist")
        return format_html('<a href="{}?call__id__exact={}">{}</a>', url, obj.id, count)

    participants_count_display.short_description = _("Participants")

    def duration_display(self, obj):
        """Duration display."""
        return obj.get_duration_display()

    duration_display.short_description = _("Duration")


@admin.register(ChatPoll)
class ChatPollAdmin(admin.ModelAdmin):
    """Admin interface for ChatPoll model."""

    list_display = (
        "id",
        "question_short",
        "type",
        "is_anonymous",
        "total_voter_count",
        "is_closed",
        "created_at",
    )
    list_filter = ("type", "is_anonymous", "is_closed", "created_at")
    search_fields = ("question", "explanation")
    readonly_fields = ("total_voter_count", "created_at")
    autocomplete_fields = ["message"]

    def question_short(self, obj):
        """Short question."""
        return obj.question[:50] + ("..." if len(obj.question) > 50 else "")

    question_short.short_description = _("Question")


@admin.register(ChatStickerSet)
class ChatStickerSetAdmin(admin.ModelAdmin):
    """Admin interface for ChatStickerSet model."""

    list_display = (
        "name",
        "title",
        "type",
        "creator",
        "stickers_count",
        "install_count",
        "is_official",
        "created_at",
    )
    list_filter = ("type", "is_official", "is_masks", "is_premium", "created_at")
    search_fields = ("name", "title", "creator__username")
    readonly_fields = ("install_count", "created_at", "stickers_count_display")
    autocomplete_fields = ["creator"]

    def stickers_count(self, obj):
        """Stickers count."""
        return obj.stickers.count()

    stickers_count.short_description = _("Stickers")

    def stickers_count_display(self, obj):
        """Stickers count with link."""
        count = obj.stickers.count()
        url = reverse("admin:chats_chatsticker_changelist")
        return format_html(
            '<a href="{}?sticker_set__id__exact={}">{}</a>', url, obj.id, count
        )

    stickers_count_display.short_description = _("Stickers")


@admin.register(ChatModerationLog)
class ChatModerationLogAdmin(admin.ModelAdmin):
    """Admin interface for ChatModerationLog model."""

    list_display = (
        "id",
        "chat_link",
        "action",
        "moderator",
        "target_user",
        "reason_short",
        "created_at",
    )
    list_filter = ("action", "created_at")
    search_fields = (
        "reason",
        "moderator__username",
        "target_user__username",
        "chat__name",
    )
    readonly_fields = ("created_at",)
    autocomplete_fields = ["chat", "moderator", "target_user", "target_message"]

    def chat_link(self, obj):
        """Link to chat admin."""
        url = reverse("admin:chats_chat_change", args=[obj.chat.id])
        return format_html(
            '<a href="{}">{}</a>', url, obj.chat.name or str(obj.chat.id)[:8]
        )

    chat_link.short_description = _("Chat")

    def reason_short(self, obj):
        """Short reason."""
        return (
            obj.reason[:50] + ("..." if len(obj.reason) > 50 else "")
            if obj.reason
            else "-"
        )

    reason_short.short_description = _("Reason")


@admin.register(ChatFolder)
class ChatFolderAdmin(admin.ModelAdmin):
    """Admin interface for ChatFolder model."""

    list_display = ("name", "user", "emoji", "chats_count", "order", "created_at")
    list_filter = (
        "include_private",
        "include_groups",
        "include_channels",
        "include_bots",
        "created_at",
    )
    search_fields = ("name", "user__username")
    autocomplete_fields = ["user", "chats", "contacts", "exclude_contacts"]

    def chats_count(self, obj):
        """Chats count."""
        return obj.chats.count()

    chats_count.short_description = _("Chats")


@admin.register(ChatInviteLink)
class ChatInviteLinkAdmin(admin.ModelAdmin):
    """Admin interface for ChatInviteLink model."""

    list_display = (
        "link_short",
        "chat_link",
        "name",
        "creator",
        "is_primary",
        "usage_count",
        "member_limit",
        "is_revoked",
        "created_at",
    )
    list_filter = ("is_primary", "is_revoked", "creates_join_request", "created_at")
    search_fields = ("link", "name", "chat__name", "creator__username")
    readonly_fields = (
        "usage_count",
        "pending_join_request_count",
        "created_at",
        "revoked_at",
    )
    autocomplete_fields = ["chat", "creator"]

    def link_short(self, obj):
        """Short link display."""
        return obj.link[:20] + ("..." if len(obj.link) > 20 else "")

    link_short.short_description = _("Link")

    def chat_link(self, obj):
        """Link to chat admin."""
        url = reverse("admin:chats_chat_change", args=[obj.chat.id])
        return format_html(
            '<a href="{}">{}</a>', url, obj.chat.name or str(obj.chat.id)[:8]
        )

    chat_link.short_description = _("Chat")


@admin.register(ChatJoinRequest)
class ChatJoinRequestAdmin(admin.ModelAdmin):
    """Admin interface for ChatJoinRequest model."""

    list_display = (
        "user",
        "chat_link",
        "status",
        "approved_by",
        "bio_short",
        "created_at",
        "decided_at",
    )
    list_filter = ("status", "created_at", "decided_at")
    search_fields = ("user__username", "chat__name", "bio")
    readonly_fields = ("created_at", "decided_at")
    autocomplete_fields = ["chat", "user", "invite_link", "approved_by"]

    def chat_link(self, obj):
        """Link to chat admin."""
        url = reverse("admin:chats_chat_change", args=[obj.chat.id])
        return format_html(
            '<a href="{}">{}</a>', url, obj.chat.name or str(obj.chat.id)[:8]
        )

    chat_link.short_description = _("Chat")

    def bio_short(self, obj):
        """Short bio."""
        return obj.bio[:30] + ("..." if len(obj.bio) > 30 else "") if obj.bio else "-"

    bio_short.short_description = _("Bio")


# Register remaining models with simple admin
admin.site.register(ChatCallParticipant)
admin.site.register(ChatPollOption)
admin.site.register(ChatPollAnswer)
admin.site.register(ChatSticker)
admin.site.register(UserStickerSet)
admin.site.register(ChatTheme)

# Customize admin site
admin.site.site_header = _("Chat System Administration")
admin.site.site_title = _("Chat Admin")
admin.site.index_title = _("Welcome to Chat System Administration")
