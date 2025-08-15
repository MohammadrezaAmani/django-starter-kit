from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from django.forms import JSONField, Textarea
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from guardian.admin import GuardedModelAdmin
from mptt.admin import MPTTModelAdmin

from .models import (
    BlogAnalytics,
    BlogAttachment,
    BlogBadge,
    BlogCategory,
    BlogComment,
    BlogModerationLog,
    BlogNewsletter,
    BlogPost,
    BlogPostVersion,
    BlogReaction,
    BlogReadingList,
    BlogSeries,
    BlogSeriesPost,
    BlogSubscription,
    BlogTag,
    BlogView,
    UserBlogBadge,
)


class BlogAttachmentInline(admin.TabularInline):
    """Inline admin for blog attachments."""

    model = BlogAttachment
    extra = 0
    readonly_fields = ("size", "mime_type", "download_count", "created_at")
    fields = (
        "file",
        "url",
        "type",
        "title",
        "description",
        "alt_text",
        "caption",
        "credit",
        "copyright",
        "sort_order",
        "is_featured",
        "size",
        "mime_type",
        "download_count",
    )


class BlogPostVersionInline(admin.TabularInline):
    """Inline admin for blog post versions."""

    model = BlogPostVersion
    extra = 0
    readonly_fields = ("version_number", "created_at", "editor")
    fields = (
        "version_number",
        "title",
        "editor",
        "edit_reason",
        "is_major_edit",
        "created_at",
    )
    ordering = ("-version_number",)

    def has_add_permission(self, request, obj=None):
        return False


class BlogReactionInline(GenericTabularInline):
    """Inline admin for blog reactions."""

    model = BlogReaction
    extra = 0
    readonly_fields = ("user", "reaction_type", "created_at")
    fields = ("user", "reaction_type", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(BlogCategory)
class BlogCategoryAdmin(MPTTModelAdmin, GuardedModelAdmin):
    """Admin interface for blog categories."""

    list_display = (
        "name",
        "parent",
        "post_count",
        "view_count",
        "is_active",
        "is_featured",
        "created_at",
        "color_preview",
    )
    list_filter = ("is_active", "is_featured", "created_at", "parent")
    search_fields = ("name", "description", "seo_keywords")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("post_count", "view_count", "created_at", "updated_at")

    fieldsets = (
        (
            _("Basic Information"),
            {
                "fields": (
                    "name",
                    "slug",
                    "description",
                    "parent",
                    "color",
                    "is_active",
                    "is_featured",
                    "sort_order",
                )
            },
        ),
        (_("Media"), {"fields": ("icon", "cover_image"), "classes": ("collapse",)}),
        (
            _("SEO"),
            {
                "fields": (
                    "seo_title",
                    "seo_description",
                    "seo_keywords",
                    "canonical_url",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Statistics"),
            {"fields": ("post_count", "view_count"), "classes": ("collapse",)},
        ),
        (
            _("Metadata"),
            {
                "fields": ("created_at", "updated_at", "created_by"),
                "classes": ("collapse",),
            },
        ),
    )

    def color_preview(self, obj):
        if obj.color:
            return format_html(
                '<div style="width: 20px; height: 20px; background-color: {}; border: 1px solid #ccc;"></div>',
                obj.color,
            )
        return "-"

    color_preview.short_description = _("Color")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(BlogTag)
class BlogTagAdmin(GuardedModelAdmin):
    """Admin interface for blog tags."""

    list_display = (
        "name",
        "usage_count",
        "trending_score",
        "is_featured",
        "created_at",
        "color_preview",
    )
    list_filter = ("is_featured", "created_at")
    search_fields = ("name", "synonyms")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("usage_count", "trending_score", "created_at", "updated_at")

    fieldsets = (
        (
            _("Basic Information"),
            {
                "fields": (
                    "name",
                    "slug",
                    "description",
                    "synonyms",
                    "color",
                    "is_featured",
                )
            },
        ),
        (
            _("Statistics"),
            {"fields": ("usage_count", "trending_score"), "classes": ("collapse",)},
        ),
        (
            _("Metadata"),
            {
                "fields": ("created_at", "updated_at", "created_by"),
                "classes": ("collapse",),
            },
        ),
    )

    def color_preview(self, obj):
        if obj.color:
            return format_html(
                '<div style="width: 20px; height: 20px; background-color: {}; border: 1px solid #ccc;"></div>',
                obj.color,
            )
        return "-"

    color_preview.short_description = _("Color")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(BlogPost)
class BlogPostAdmin(GuardedModelAdmin):
    """Admin interface for blog posts."""

    list_display = (
        "title",
        "author",
        "status",
        "visibility",
        "post_type",
        "is_featured",
        "view_count",
        "like_count",
        "comment_count",
        "publish_date",
        "reading_time_display",
    )
    list_filter = (
        "status",
        "visibility",
        "post_type",
        "is_featured",
        "is_premium",
        "ai_generated",
        "language",
        "created_at",
        "publish_date",
        "categories",
        "tags",
    )
    search_fields = ("title", "subtitle", "excerpt", "raw_content")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = (
        "view_count",
        "unique_view_count",
        "like_count",
        "dislike_count",
        "comment_count",
        "share_count",
        "bookmark_count",
        "download_count",
        "word_count",
        "character_count",
        "reading_time",
        "content_hash",
        "quality_score",
        "readability_score",
        "seo_score",
        "is_trending",
        "created_at",
        "updated_at",
        "last_viewed_at",
    )
    filter_horizontal = ("categories", "tags", "co_authors")
    date_hierarchy = "publish_date"

    inlines = [BlogAttachmentInline, BlogPostVersionInline, BlogReactionInline]

    fieldsets = (
        (
            _("Basic Information"),
            {
                "fields": (
                    "title",
                    "slug",
                    "subtitle",
                    "excerpt",
                    "author",
                    "co_authors",
                    "editor",
                    "status",
                    "visibility",
                    "post_type",
                )
            },
        ),
        (
            _("Content"),
            {
                "fields": (
                    "content",
                    "content_format",
                    "raw_content",
                    "content_hash",
                    "custom_template",
                    "custom_css",
                    "custom_js",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Publishing"),
            {"fields": ("publish_date", "scheduled_date", "expiry_date")},
        ),
        (_("Categorization"), {"fields": ("categories", "tags")}),
        (
            _("Media"),
            {
                "fields": ("featured_image", "featured_image_alt", "featured_video"),
                "classes": ("collapse",),
            },
        ),
        (
            _("SEO & Social"),
            {
                "fields": (
                    "seo_title",
                    "seo_description",
                    "seo_keywords",
                    "canonical_url",
                    "meta_robots",
                    "open_graph_data",
                    "structured_data",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("AI & Automation"),
            {
                "fields": (
                    "ai_generated",
                    "ai_metadata",
                    "ai_suggestions",
                    "auto_translate",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Versioning"),
            {
                "fields": ("version", "parent_version", "version_notes"),
                "classes": ("collapse",),
            },
        ),
        (
            _("Integrations"),
            {
                "fields": (
                    "linked_project",
                    "linked_task",
                    "linked_network",
                    "linked_chat",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("A/B Testing"),
            {"fields": ("ab_test_variant", "ab_test_group"), "classes": ("collapse",)},
        ),
        (
            _("Monetization"),
            {
                "fields": (
                    "is_premium",
                    "price",
                    "currency",
                    "subscription_tiers",
                    "paywall_position",
                    "tip_enabled",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Internationalization"),
            {
                "fields": (
                    "language",
                    "languages",
                    "translations",
                    "translation_parent",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Content Quality"),
            {
                "fields": (
                    "quality_score",
                    "readability_score",
                    "seo_score",
                    "word_count",
                    "character_count",
                    "reading_time",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Moderation"),
            {
                "fields": (
                    "is_featured",
                    "is_trending",
                    "is_editors_choice",
                    "is_sponsored",
                    "moderation_notes",
                    "content_warnings",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Settings"),
            {
                "fields": (
                    "search_boost",
                    "allow_indexing",
                    "allow_comments",
                    "allow_reactions",
                    "allow_shares",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Statistics"),
            {
                "fields": (
                    "view_count",
                    "unique_view_count",
                    "like_count",
                    "dislike_count",
                    "comment_count",
                    "share_count",
                    "bookmark_count",
                    "download_count",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Metadata"),
            {
                "fields": (
                    "created_at",
                    "updated_at",
                    "last_viewed_at",
                    "last_modified_by",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    formfield_overrides = {
        JSONField: {"widget": Textarea(attrs={"rows": 4, "cols": 80})},
    }

    def reading_time_display(self, obj):
        return obj.get_reading_time_display()

    reading_time_display.short_description = _("Reading Time")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.author = request.user
        obj.last_modified_by = request.user
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("author", "editor", "last_modified_by")
            .prefetch_related("categories", "tags", "co_authors")
        )

    actions = ["publish_posts", "archive_posts", "feature_posts", "unfeature_posts"]

    def publish_posts(self, request, queryset):
        updated = queryset.update(
            status=BlogPost.PostStatus.PUBLISHED, publish_date=timezone.now()
        )
        self.message_user(request, f"{updated} posts were published.")

    publish_posts.short_description = _("Publish selected posts")

    def archive_posts(self, request, queryset):
        updated = queryset.update(status=BlogPost.PostStatus.ARCHIVED)
        self.message_user(request, f"{updated} posts were archived.")

    archive_posts.short_description = _("Archive selected posts")

    def feature_posts(self, request, queryset):
        updated = queryset.update(is_featured=True)
        self.message_user(request, f"{updated} posts were featured.")

    feature_posts.short_description = _("Feature selected posts")

    def unfeature_posts(self, request, queryset):
        updated = queryset.update(is_featured=False)
        self.message_user(request, f"{updated} posts were unfeatured.")

    unfeature_posts.short_description = _("Unfeature selected posts")


@admin.register(BlogPostVersion)
class BlogPostVersionAdmin(admin.ModelAdmin):
    """Admin interface for blog post versions."""

    list_display = (
        "post",
        "version_number",
        "title",
        "editor",
        "is_major_edit",
        "created_at",
    )
    list_filter = ("is_major_edit", "created_at", "post__author")
    search_fields = ("post__title", "title", "changes_summary", "edit_reason")
    readonly_fields = ("created_at",)

    fieldsets = (
        (
            _("Version Information"),
            {
                "fields": (
                    "post",
                    "version_number",
                    "title",
                    "editor",
                    "edit_reason",
                    "is_major_edit",
                )
            },
        ),
        (
            _("Content"),
            {"fields": ("content", "raw_content"), "classes": ("collapse",)},
        ),
        (
            _("Changes"),
            {"fields": ("changes_summary", "changes_diff"), "classes": ("collapse",)},
        ),
        (_("Metadata"), {"fields": ("created_at",), "classes": ("collapse",)}),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(BlogAttachment)
class BlogAttachmentAdmin(admin.ModelAdmin):
    """Admin interface for blog attachments."""

    list_display = (
        "title",
        "post",
        "type",
        "size_display",
        "mime_type",
        "is_featured",
        "download_count",
        "created_at",
    )
    list_filter = ("type", "is_featured", "created_at", "mime_type")
    search_fields = ("title", "description", "post__title")
    readonly_fields = ("size", "mime_type", "download_count", "created_at")

    fieldsets = (
        (
            _("Basic Information"),
            {"fields": ("post", "file", "url", "type", "title", "description")},
        ),
        (
            _("Media Information"),
            {"fields": ("alt_text", "caption", "credit", "copyright", "metadata")},
        ),
        (_("Display"), {"fields": ("sort_order", "is_featured")}),
        (
            _("Statistics"),
            {
                "fields": ("size", "mime_type", "download_count"),
                "classes": ("collapse",),
            },
        ),
        (
            _("Metadata"),
            {"fields": ("created_at", "uploaded_by"), "classes": ("collapse",)},
        ),
    )

    def size_display(self, obj):
        if obj.size:
            if obj.size < 1024:
                return f"{obj.size} B"
            elif obj.size < 1024 * 1024:
                return f"{obj.size / 1024:.1f} KB"
            else:
                return f"{obj.size / (1024 * 1024):.1f} MB"
        return "-"

    size_display.short_description = _("Size")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(BlogComment)
class BlogCommentAdmin(GuardedModelAdmin):
    """Admin interface for blog comments."""

    list_display = (
        "content_preview",
        "author",
        "post",
        "status",
        "like_count",
        "reply_count",
        "is_pinned",
        "created_at",
    )
    list_filter = (
        "status",
        "is_pinned",
        "is_highlighted",
        "content_format",
        "created_at",
        "post__categories",
    )
    search_fields = ("content", "author__username", "post__title")
    readonly_fields = (
        "like_count",
        "dislike_count",
        "reply_count",
        "is_edited",
        "edit_count",
        "flagged_count",
        "spam_score",
        "created_at",
        "updated_at",
    )

    inlines = [BlogReactionInline]

    fieldsets = (
        (
            _("Basic Information"),
            {
                "fields": (
                    "post",
                    "author",
                    "parent",
                    "content",
                    "content_format",
                    "status",
                )
            },
        ),
        (
            _("Moderation"),
            {
                "fields": (
                    "is_pinned",
                    "is_highlighted",
                    "moderation_notes",
                    "flagged_count",
                    "spam_score",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Edit Tracking"),
            {
                "fields": ("is_edited", "edit_count", "edit_history"),
                "classes": ("collapse",),
            },
        ),
        (
            _("Engagement"),
            {
                "fields": ("like_count", "dislike_count", "reply_count", "reactions"),
                "classes": ("collapse",),
            },
        ),
        (
            _("Technical"),
            {"fields": ("ip_address", "user_agent"), "classes": ("collapse",)},
        ),
        (
            _("Metadata"),
            {
                "fields": ("created_at", "updated_at", "approved_at", "approved_by"),
                "classes": ("collapse",),
            },
        ),
    )

    def content_preview(self, obj):
        return obj.content[:100] + ("..." if len(obj.content) > 100 else "")

    content_preview.short_description = _("Content")

    actions = ["approve_comments", "reject_comments", "mark_as_spam"]

    def approve_comments(self, request, queryset):
        updated = queryset.update(
            status=BlogComment.CommentStatus.APPROVED,
            approved_at=timezone.now(),
            approved_by=request.user,
        )
        self.message_user(request, f"{updated} comments were approved.")

    approve_comments.short_description = _("Approve selected comments")

    def reject_comments(self, request, queryset):
        updated = queryset.update(status=BlogComment.CommentStatus.REJECTED)
        self.message_user(request, f"{updated} comments were rejected.")

    reject_comments.short_description = _("Reject selected comments")

    def mark_as_spam(self, request, queryset):
        updated = queryset.update(status=BlogComment.CommentStatus.SPAM)
        self.message_user(request, f"{updated} comments were marked as spam.")

    mark_as_spam.short_description = _("Mark selected comments as spam")


@admin.register(BlogReaction)
class BlogReactionAdmin(admin.ModelAdmin):
    """Admin interface for blog reactions."""

    list_display = ("user", "content_object", "reaction_type", "created_at")
    list_filter = ("reaction_type", "created_at", "content_type")
    search_fields = ("user__username",)
    readonly_fields = ("created_at",)

    def has_add_permission(self, request):
        return False


@admin.register(BlogView)
class BlogViewAdmin(admin.ModelAdmin):
    """Admin interface for blog views."""

    list_display = (
        "post",
        "user",
        "device_type",
        "country",
        "duration_display",
        "scroll_depth",
        "is_bounce",
        "created_at",
    )
    list_filter = ("device_type", "country", "is_bounce", "created_at")
    search_fields = ("post__title", "user__username", "referrer", "utm_source")
    readonly_fields = ("created_at",)

    def duration_display(self, obj):
        if obj.duration:
            minutes = obj.duration // 60
            seconds = obj.duration % 60
            return f"{minutes}m {seconds}s"
        return "-"

    duration_display.short_description = _("Duration")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(BlogSubscription)
class BlogSubscriptionAdmin(admin.ModelAdmin):
    """Admin interface for blog subscriptions."""

    list_display = (
        "user",
        "subscription_type",
        "subscribed_to",
        "notification_frequency",
        "is_active",
        "created_at",
    )
    list_filter = (
        "subscription_type",
        "notification_frequency",
        "is_active",
        "email_notifications",
        "push_notifications",
        "created_at",
    )
    search_fields = ("user__username",)
    readonly_fields = (
        "unsubscribe_token",
        "created_at",
        "updated_at",
        "last_notification_sent",
    )

    fieldsets = (
        (
            _("Subscription Details"),
            {"fields": ("user", "subscription_type", "content_type", "object_id")},
        ),
        (
            _("Notification Preferences"),
            {
                "fields": (
                    "email_notifications",
                    "push_notifications",
                    "in_app_notifications",
                    "notification_frequency",
                )
            },
        ),
        (_("Status"), {"fields": ("is_active", "unsubscribe_token")}),
        (
            _("Metadata"),
            {
                "fields": ("created_at", "updated_at", "last_notification_sent"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(BlogAnalytics)
class BlogAnalyticsAdmin(admin.ModelAdmin):
    """Admin interface for blog analytics."""

    list_display = (
        "post",
        "total_views",
        "unique_views",
        "engagement_rate",
        "bounce_rate",
        "avg_reading_time",
        "last_updated",
    )
    list_filter = ("last_updated", "last_calculated")
    search_fields = ("post__title",)
    readonly_fields = (
        "total_views",
        "unique_views",
        "total_likes",
        "total_comments",
        "total_shares",
        "total_bookmarks",
        "engagement_rate",
        "bounce_rate",
        "avg_reading_time",
        "completion_rate",
        "last_updated",
        "last_calculated",
    )

    fieldsets = (
        (
            _("Basic Metrics"),
            {
                "fields": (
                    "post",
                    "total_views",
                    "unique_views",
                    "total_likes",
                    "total_comments",
                    "total_shares",
                    "total_bookmarks",
                )
            },
        ),
        (
            _("Engagement"),
            {
                "fields": (
                    "engagement_rate",
                    "bounce_rate",
                    "avg_reading_time",
                    "completion_rate",
                )
            },
        ),
        (
            _("SEO Metrics"),
            {
                "fields": (
                    "search_impressions",
                    "search_clicks",
                    "search_ctr",
                    "avg_search_position",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Traffic Sources"),
            {
                "fields": (
                    "direct_traffic",
                    "search_traffic",
                    "social_traffic",
                    "referral_traffic",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Geographic Data"),
            {"fields": ("top_countries", "top_cities"), "classes": ("collapse",)},
        ),
        (
            _("Device Data"),
            {
                "fields": ("desktop_views", "mobile_views", "tablet_views"),
                "classes": ("collapse",),
            },
        ),
        (
            _("AI Insights"),
            {
                "fields": (
                    "content_quality_score",
                    "readability_score",
                    "seo_score",
                    "sentiment_score",
                    "trending_score",
                    "virality_prediction",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Predictions"),
            {
                "fields": ("predicted_views_7d", "predicted_views_30d"),
                "classes": ("collapse",),
            },
        ),
        (
            _("Metadata"),
            {"fields": ("last_updated", "last_calculated"), "classes": ("collapse",)},
        ),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    actions = ["update_analytics"]

    def update_analytics(self, request, queryset):
        updated = 0
        for analytics in queryset:
            analytics.update_metrics()
            updated += 1
        self.message_user(request, f"{updated} analytics records were updated.")

    update_analytics.short_description = _("Update analytics for selected posts")


class BlogSeriesPostInline(admin.TabularInline):
    """Inline admin for blog series posts."""

    model = BlogSeriesPost
    extra = 0
    ordering = ("order",)


@admin.register(BlogSeries)
class BlogSeriesAdmin(GuardedModelAdmin):
    """Admin interface for blog series."""

    list_display = (
        "title",
        "author",
        "posts_count",
        "is_active",
        "is_completed",
        "created_at",
    )
    list_filter = ("is_active", "is_completed", "created_at")
    search_fields = ("title", "description", "author__username")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at")

    inlines = [BlogSeriesPostInline]

    def posts_count(self, obj):
        return obj.posts.count()

    posts_count.short_description = _("Posts Count")


@admin.register(BlogNewsletter)
class BlogNewsletterAdmin(admin.ModelAdmin):
    """Admin interface for blog newsletters."""

    list_display = (
        "subject",
        "status",
        "recipient_count",
        "open_rate",
        "click_rate",
        "scheduled_date",
        "sent_date",
    )
    list_filter = ("status", "scheduled_date", "sent_date", "created_at")
    search_fields = ("subject",)
    readonly_fields = (
        "recipient_count",
        "open_rate",
        "click_rate",
        "sent_date",
        "created_at",
    )
    filter_horizontal = ("featured_posts",)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(BlogBadge)
class BlogBadgeAdmin(admin.ModelAdmin):
    """Admin interface for blog badges."""

    list_display = ("name", "badge_type", "level", "points", "is_active", "created_at")
    list_filter = ("badge_type", "level", "is_active", "created_at")
    search_fields = ("name", "description")
    readonly_fields = ("created_at",)


@admin.register(UserBlogBadge)
class UserBlogBadgeAdmin(admin.ModelAdmin):
    """Admin interface for user blog badges."""

    list_display = ("user", "badge", "earned_at")
    list_filter = ("badge__badge_type", "badge__level", "earned_at")
    search_fields = ("user__username", "badge__name")
    readonly_fields = ("earned_at",)

    def has_add_permission(self, request):
        return False


@admin.register(BlogModerationLog)
class BlogModerationLogAdmin(admin.ModelAdmin):
    """Admin interface for blog moderation logs."""

    list_display = ("moderator", "action_type", "content_object", "created_at")
    list_filter = ("action_type", "created_at", "content_type")
    search_fields = ("moderator__username", "reason", "notes")
    readonly_fields = ("created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(BlogReadingList)
class BlogReadingListAdmin(admin.ModelAdmin):
    """Admin interface for blog reading lists."""

    list_display = (
        "user",
        "name",
        "privacy",
        "posts_count",
        "is_default",
        "created_at",
    )
    list_filter = ("privacy", "is_default", "created_at")
    search_fields = ("user__username", "name", "description")
    readonly_fields = ("created_at", "updated_at")
    filter_horizontal = ("posts",)

    def posts_count(self, obj):
        return obj.posts.count()

    posts_count.short_description = _("Posts Count")


# Customize admin site header and title
admin.site.site_header = _("Blog Administration")
admin.site.site_title = _("Blog Admin")
admin.site.index_title = _("Welcome to Blog Administration")
