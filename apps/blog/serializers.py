import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.accounts.serializers import UserProfileSerializer

from .exceptions import (
    ContentTooLong,
    ContentTooShort,
    MaxCategoriesExceeded,
    MaxTagsExceeded,
)
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
    BlogSubscription,
    BlogTag,
    BlogView,
    UserBlogBadge,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class BlogCategorySerializer(serializers.ModelSerializer):
    """Serializer for blog categories."""

    posts_count = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()
    breadcrumbs = serializers.SerializerMethodField()
    level = serializers.ReadOnlyField()

    class Meta:
        model = BlogCategory
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "parent",
            "is_active",
            "meta_title",
            "meta_description",
            "image",
            "color",
            "icon",
            "sort_order",
            "posts_count",
            "children",
            "breadcrumbs",
            "level",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "slug", "created_at", "updated_at", "level"]

    def get_posts_count(self, obj):
        """Get the number of published posts in this category."""
        return obj.get_posts_count()

    def get_children(self, obj):
        """Get child categories."""
        children = obj.get_children().filter(is_active=True)
        return BlogCategorySerializer(children, many=True, context=self.context).data

    def get_breadcrumbs(self, obj):
        """Get category breadcrumbs."""
        return obj.get_breadcrumbs()

    def validate_parent(self, value):
        """Validate parent category to prevent circular references."""
        if value and self.instance:
            if value == self.instance:
                raise ValidationError("A category cannot be its own parent.")
            if self.instance in value.get_ancestors(include_self=True):
                raise ValidationError("Cannot create circular reference.")
        return value


class BlogCategoryTreeSerializer(serializers.ModelSerializer):
    """Serializer for category tree structure."""

    children = serializers.SerializerMethodField()
    posts_count = serializers.SerializerMethodField()

    class Meta:
        model = BlogCategory
        fields = ["id", "name", "slug", "children", "posts_count", "level"]

    def get_children(self, obj):
        children = obj.get_children().filter(is_active=True)
        return BlogCategoryTreeSerializer(children, many=True).data

    def get_posts_count(self, obj):
        return obj.get_posts_count()


class BlogTagSerializer(serializers.ModelSerializer):
    """Serializer for blog tags."""

    usage_count = serializers.ReadOnlyField()
    trending_score = serializers.SerializerMethodField()

    class Meta:
        model = BlogTag
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "color",
            "is_featured",
            "usage_count",
            "trending_score",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "slug", "usage_count", "created_at", "updated_at"]

    def get_trending_score(self, obj):
        """Calculate trending score based on recent usage."""
        recent_usage = BlogPost.objects.filter(
            tags=obj,
            created_at__gte=timezone.now() - timedelta(days=7),
            status=BlogPost.PostStatus.PUBLISHED,
        ).count()
        return recent_usage


class BlogAttachmentSerializer(serializers.ModelSerializer):
    """Serializer for blog attachments."""

    download_url = serializers.SerializerMethodField()
    file_size_display = serializers.SerializerMethodField()

    class Meta:
        model = BlogAttachment
        fields = [
            "id",
            "file",
            "original_name",
            "file_type",
            "file_size",
            "file_size_display",
            "description",
            "alt_text",
            "download_url",
            "created_at",
        ]
        read_only_fields = ["id", "file_size", "created_at"]

    def get_download_url(self, obj):
        """Get download URL for the attachment."""
        return obj.get_download_url()

    def get_file_size_display(self, obj):
        """Get human-readable file size."""
        if obj.file_size < 1024:
            return f"{obj.file_size} B"
        elif obj.file_size < 1024 * 1024:
            return f"{obj.file_size / 1024:.1f} KB"
        else:
            return f"{obj.file_size / (1024 * 1024):.1f} MB"

    def validate_file(self, value):
        """Validate uploaded file."""
        max_size = 10 * 1024 * 1024  # 10MB
        if value.size > max_size:
            raise ValidationError("File size cannot exceed 10MB.")

        allowed_types = [
            "image/jpeg",
            "image/png",
            "image/gif",
            "application/pdf",
            "text/plain",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ]
        if value.content_type not in allowed_types:
            raise ValidationError("File type not allowed.")

        return value


class BlogPostVersionSerializer(serializers.ModelSerializer):
    """Serializer for blog post versions."""

    created_by_display = serializers.CharField(
        source="created_by.get_full_name", read_only=True
    )

    class Meta:
        model = BlogPostVersion
        fields = [
            "id",
            "version_number",
            "title",
            "content",
            "summary",
            "change_reason",
            "created_by",
            "created_by_display",
            "created_at",
        ]
        read_only_fields = ["id", "version_number", "created_by", "created_at"]


class BlogReactionSerializer(serializers.ModelSerializer):
    """Serializer for blog reactions."""

    user_display = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = BlogReaction
        fields = [
            "id",
            "reaction_type",
            "user",
            "user_display",
            "created_at",
        ]
        read_only_fields = ["id", "user", "created_at"]

    def create(self, validated_data):
        """Create reaction and prevent duplicates."""
        user = self.context["request"].user
        post = self.context["post"]

        # Check if user already reacted
        existing_reaction = BlogReaction.objects.filter(user=user, post=post).first()

        if existing_reaction:
            # Update existing reaction
            existing_reaction.reaction_type = validated_data["reaction_type"]
            existing_reaction.save()
            return existing_reaction
        else:
            # Create new reaction
            validated_data["user"] = user
            validated_data["post"] = post
            return super().create(validated_data)


class BlogCommentSerializer(serializers.ModelSerializer):
    """Serializer for blog comments."""

    author_display = serializers.CharField(
        source="author.get_full_name", read_only=True
    )
    author_avatar = serializers.ImageField(
        source="author.userprofile.avatar", read_only=True
    )
    replies = serializers.SerializerMethodField()
    replies_count = serializers.SerializerMethodField()
    depth = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    is_author = serializers.SerializerMethodField()

    class Meta:
        model = BlogComment
        fields = [
            "id",
            "content",
            "parent",
            "author",
            "author_display",
            "author_avatar",
            "status",
            "is_pinned",
            "replies",
            "replies_count",
            "depth",
            "can_edit",
            "can_delete",
            "is_author",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "author", "created_at", "updated_at"]

    def get_replies(self, obj):
        """Get comment replies."""
        if obj.replies.exists():
            replies = obj.replies.filter(
                status=BlogComment.CommentStatus.APPROVED
            ).order_by("created_at")
            return BlogCommentSerializer(replies, many=True, context=self.context).data
        return []

    def get_replies_count(self, obj):
        """Get replies count."""
        return obj.replies.filter(status=BlogComment.CommentStatus.APPROVED).count()

    def get_depth(self, obj):
        """Get comment depth in thread."""
        return obj.get_depth()

    def get_can_edit(self, obj):
        """Check if current user can edit this comment."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.can_be_edited_by(request.user)

    def get_can_delete(self, obj):
        """Check if current user can delete this comment."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.can_be_deleted_by(request.user)

    def get_is_author(self, obj):
        """Check if current user is the comment author."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.author == request.user

    def validate_content(self, value):
        """Validate comment content."""
        if len(value.strip()) < 10:
            raise ContentTooShort("Comment must be at least 10 characters long.")
        if len(value) > 5000:
            raise ContentTooLong("Comment cannot exceed 5000 characters.")
        return value.strip()

    def validate_parent(self, value):
        """Validate parent comment."""
        if value:
            # Check maximum depth
            max_depth = 5
            if value.get_depth() >= max_depth:
                raise ValidationError(f"Maximum comment depth ({max_depth}) exceeded.")

            # Ensure parent belongs to the same post
            post = self.context.get("post")
            if post and value.post != post:
                raise ValidationError("Parent comment must belong to the same post.")
        return value


class BlogPostListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for blog post lists."""

    author_display = serializers.CharField(
        source="author.get_full_name", read_only=True
    )
    author_avatar = serializers.ImageField(
        source="author.userprofile.avatar", read_only=True
    )
    categories = BlogCategorySerializer(many=True, read_only=True)
    tags = BlogTagSerializer(many=True, read_only=True)
    reading_time = serializers.SerializerMethodField()
    excerpt = serializers.SerializerMethodField()
    reactions_count = serializers.SerializerMethodField()
    comments_count = serializers.SerializerMethodField()
    views_count = serializers.SerializerMethodField()
    is_bookmarked = serializers.SerializerMethodField()

    class Meta:
        model = BlogPost
        fields = [
            "id",
            "title",
            "slug",
            "excerpt",
            "featured_image",
            "author",
            "author_display",
            "author_avatar",
            "categories",
            "tags",
            "status",
            "visibility",
            "is_featured",
            "is_trending",
            "reading_time",
            "reactions_count",
            "comments_count",
            "views_count",
            "is_bookmarked",
            "published_at",
            "created_at",
            "updated_at",
        ]

    def get_reading_time(self, obj):
        """Get reading time display."""
        return obj.get_reading_time_display()

    def get_excerpt(self, obj):
        """Get post excerpt."""
        if obj.excerpt:
            return obj.excerpt
        # Generate excerpt from content
        from django.utils.html import strip_tags

        content = strip_tags(obj.content)
        return content[:200] + "..." if len(content) > 200 else content

    def get_reactions_count(self, obj):
        """Get total reactions count."""
        return obj.reactions.count()

    def get_comments_count(self, obj):
        """Get approved comments count."""
        return obj.comments.filter(status=BlogComment.CommentStatus.APPROVED).count()

    def get_views_count(self, obj):
        """Get views count."""
        return obj.views.count()

    def get_is_bookmarked(self, obj):
        """Check if current user bookmarked this post."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return BlogReadingList.objects.filter(user=request.user, posts=obj).exists()


class BlogPostDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for blog posts."""

    author = UserProfileSerializer(source="author.userprofile", read_only=True)
    categories = BlogCategorySerializer(many=True, read_only=True)
    tags = BlogTagSerializer(many=True, read_only=True)
    attachments = BlogAttachmentSerializer(many=True, read_only=True)
    versions = BlogPostVersionSerializer(many=True, read_only=True)
    comments = serializers.SerializerMethodField()
    reactions = serializers.SerializerMethodField()
    related_posts = serializers.SerializerMethodField()
    reading_time = serializers.SerializerMethodField()
    analytics = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    is_author = serializers.SerializerMethodField()
    user_reaction = serializers.SerializerMethodField()
    series_info = serializers.SerializerMethodField()

    class Meta:
        model = BlogPost
        fields = [
            "id",
            "title",
            "slug",
            "content",
            "excerpt",
            "featured_image",
            "author",
            "categories",
            "tags",
            "attachments",
            "status",
            "visibility",
            "post_type",
            "content_format",
            "is_featured",
            "is_trending",
            "allow_comments",
            "is_commentable",
            "meta_title",
            "meta_description",
            "reading_time",
            "versions",
            "comments",
            "reactions",
            "related_posts",
            "analytics",
            "can_edit",
            "can_delete",
            "is_author",
            "user_reaction",
            "series_info",
            "published_at",
            "created_at",
            "updated_at",
        ]

    def get_comments(self, obj):
        """Get top-level comments."""
        comments = obj.comments.filter(
            parent__isnull=True, status=BlogComment.CommentStatus.APPROVED
        ).order_by("-created_at")[:10]
        return BlogCommentSerializer(comments, many=True, context=self.context).data

    def get_reactions(self, obj):
        """Get reactions summary."""
        reactions = obj.reactions.values("reaction_type").annotate(
            count=models.Count("id")
        )
        return {reaction["reaction_type"]: reaction["count"] for reaction in reactions}

    def get_related_posts(self, obj):
        """Get related posts."""
        related = obj.get_related_posts()[:5]
        return BlogPostListSerializer(related, many=True, context=self.context).data

    def get_reading_time(self, obj):
        """Get reading time display."""
        return obj.get_reading_time_display()

    def get_analytics(self, obj):
        """Get post analytics (only for author and moderators)."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None

        if obj.author == request.user or request.user.is_staff:
            try:
                analytics = obj.analytics
                return {
                    "views_count": analytics.views_count,
                    "unique_views_count": analytics.unique_views_count,
                    "engagement_rate": analytics.calculate_engagement_rate(),
                    "bounce_rate": analytics.calculate_bounce_rate(),
                }
            except BlogAnalytics.DoesNotExist:
                return None
        return None

    def get_can_edit(self, obj):
        """Check if current user can edit this post."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.author == request.user or request.user.is_staff

    def get_can_delete(self, obj):
        """Check if current user can delete this post."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.author == request.user or request.user.is_superuser

    def get_is_author(self, obj):
        """Check if current user is the post author."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.author == request.user

    def get_user_reaction(self, obj):
        """Get current user's reaction to this post."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None

        reaction = obj.reactions.filter(user=request.user).first()
        return reaction.reaction_type if reaction else None

    def get_series_info(self, obj):
        """Get series information if post is part of a series."""
        series_post = obj.series_posts.first()
        if series_post:
            return {
                "series_id": series_post.series.id,
                "series_title": series_post.series.title,
                "series_slug": series_post.series.slug,
                "order": series_post.order,
                "total_posts": series_post.series.posts.count(),
            }
        return None


class BlogPostCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating blog posts."""

    category_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
        allow_empty=True,
    )
    tag_names = serializers.ListField(
        child=serializers.CharField(max_length=50),
        write_only=True,
        required=False,
        allow_empty=True,
    )

    class Meta:
        model = BlogPost
        fields = [
            "title",
            "content",
            "excerpt",
            "featured_image",
            "status",
            "visibility",
            "post_type",
            "content_format",
            "allow_comments",
            "is_commentable",
            "meta_title",
            "meta_description",
            "category_ids",
            "tag_names",
            "published_at",
        ]

    def validate_title(self, value):
        """Validate post title."""
        if len(value.strip()) < 5:
            raise ContentTooShort("Title must be at least 5 characters long.")
        if len(value) > 200:
            raise ContentTooLong("Title cannot exceed 200 characters.")
        return value.strip()

    def validate_content(self, value):
        """Validate post content."""
        if len(value.strip()) < 100:
            raise ContentTooShort("Content must be at least 100 characters long.")
        if len(value) > 100000:
            raise ContentTooLong("Content cannot exceed 100,000 characters.")
        return value.strip()

    def validate_category_ids(self, value):
        """Validate category IDs."""
        if len(value) > 5:
            raise MaxCategoriesExceeded("Maximum 5 categories allowed per post.")

        # Check if all categories exist and are active
        existing_categories = BlogCategory.objects.filter(
            id__in=value, is_active=True
        ).values_list("id", flat=True)

        invalid_ids = set(value) - set(existing_categories)
        if invalid_ids:
            raise ValidationError(f"Invalid category IDs: {list(invalid_ids)}")

        return value

    def validate_tag_names(self, value):
        """Validate tag names."""
        if len(value) > 10:
            raise MaxTagsExceeded("Maximum 10 tags allowed per post.")

        # Validate each tag name
        for tag_name in value:
            if len(tag_name.strip()) < 2:
                raise ValidationError(
                    f"Tag '{tag_name}' is too short (minimum 2 characters)."
                )
            if len(tag_name) > 50:
                raise ValidationError(
                    f"Tag '{tag_name}' is too long (maximum 50 characters)."
                )

        return [tag.strip().lower() for tag in value]

    def validate(self, attrs):
        """Cross-field validation."""
        status = attrs.get("status")
        published_at = attrs.get("published_at")

        # If publishing, ensure published_at is set
        if status == BlogPost.PostStatus.PUBLISHED and not published_at:
            attrs["published_at"] = timezone.now()

        # If setting to draft, clear published_at
        if status == BlogPost.PostStatus.DRAFT:
            attrs["published_at"] = None

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """Create blog post with categories and tags."""
        category_ids = validated_data.pop("category_ids", [])
        tag_names = validated_data.pop("tag_names", [])

        # Set author
        validated_data["author"] = self.context["request"].user

        # Create post
        post = super().create(validated_data)

        # Add categories
        if category_ids:
            categories = BlogCategory.objects.filter(id__in=category_ids)
            post.categories.set(categories)

        # Add tags
        if tag_names:
            tags = []
            for tag_name in tag_names:
                tag, created = BlogTag.objects.get_or_create(
                    name=tag_name, defaults={"created_by": self.context["request"].user}
                )
                tags.append(tag)
            post.tags.set(tags)

        return post

    @transaction.atomic
    def update(self, instance, validated_data):
        """Update blog post with categories and tags."""
        category_ids = validated_data.pop("category_ids", None)
        tag_names = validated_data.pop("tag_names", None)

        # Create version before updating
        if instance.pk:
            BlogPostVersion.objects.create(
                post=instance,
                title=instance.title,
                content=instance.content,
                summary=instance.excerpt or "",
                change_reason="Updated via API",
                created_by=self.context["request"].user,
            )

        # Update post
        post = super().update(instance, validated_data)

        # Update categories
        if category_ids is not None:
            categories = BlogCategory.objects.filter(id__in=category_ids)
            post.categories.set(categories)

        # Update tags
        if tag_names is not None:
            tags = []
            for tag_name in tag_names:
                tag, created = BlogTag.objects.get_or_create(
                    name=tag_name, defaults={"created_by": self.context["request"].user}
                )
                tags.append(tag)
            post.tags.set(tags)

        return post


class BlogSeriesSerializer(serializers.ModelSerializer):
    """Serializer for blog series."""

    author_display = serializers.CharField(
        source="author.get_full_name", read_only=True
    )
    posts_count = serializers.SerializerMethodField()
    total_reading_time = serializers.SerializerMethodField()
    posts = serializers.SerializerMethodField()

    class Meta:
        model = BlogSeries
        fields = [
            "id",
            "title",
            "slug",
            "description",
            "author",
            "author_display",
            "cover_image",
            "is_active",
            "posts_count",
            "total_reading_time",
            "posts",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "slug", "author", "created_at", "updated_at"]

    def get_posts_count(self, obj):
        """Get number of posts in series."""
        return obj.posts.filter(status=BlogPost.PostStatus.PUBLISHED).count()

    def get_total_reading_time(self, obj):
        """Get total reading time for all posts in series."""
        total_words = sum(
            post.reading_time
            for post in obj.posts.filter(status=BlogPost.PostStatus.PUBLISHED)
        )
        return f"{total_words // 200} min read"

    def get_posts(self, obj):
        """Get posts in series ordered by series order."""
        series_posts = (
            obj.blogseriespost_set.filter(post__status=BlogPost.PostStatus.PUBLISHED)
            .order_by("order")
            .select_related("post")
        )

        posts_data = []
        for series_post in series_posts:
            post_data = BlogPostListSerializer(
                series_post.post, context=self.context
            ).data
            post_data["series_order"] = series_post.order
            posts_data.append(post_data)

        return posts_data


class BlogSubscriptionSerializer(serializers.ModelSerializer):
    """Serializer for blog subscriptions."""

    class Meta:
        model = BlogSubscription
        fields = [
            "id",
            "subscription_type",
            "notification_frequency",
            "is_active",
            "subscribed_at",
        ]
        read_only_fields = ["id", "user", "subscribed_at"]

    def create(self, validated_data):
        """Create subscription for current user."""
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class BlogAnalyticsSerializer(serializers.ModelSerializer):
    """Serializer for blog analytics."""

    engagement_rate = serializers.SerializerMethodField()
    bounce_rate = serializers.SerializerMethodField()

    class Meta:
        model = BlogAnalytics
        fields = [
            "views_count",
            "unique_views_count",
            "shares_count",
            "time_spent_total",
            "time_spent_average",
            "engagement_rate",
            "bounce_rate",
            "last_updated",
        ]

    def get_engagement_rate(self, obj):
        """Get engagement rate."""
        return obj.calculate_engagement_rate()

    def get_bounce_rate(self, obj):
        """Get bounce rate."""
        return obj.calculate_bounce_rate()


class BlogModerationLogSerializer(serializers.ModelSerializer):
    """Serializer for blog moderation logs."""

    moderator_display = serializers.CharField(
        source="moderator.get_full_name", read_only=True
    )
    content_type_display = serializers.CharField(
        source="content_type.model", read_only=True
    )

    class Meta:
        model = BlogModerationLog
        fields = [
            "id",
            "moderator",
            "moderator_display",
            "action_type",
            "content_type",
            "content_type_display",
            "object_id",
            "description",
            "ip_address",
            "user_agent",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class BlogNewsletterSerializer(serializers.ModelSerializer):
    """Serializer for blog newsletters."""

    sent_count = serializers.SerializerMethodField()
    open_rate = serializers.SerializerMethodField()
    click_rate = serializers.SerializerMethodField()

    class Meta:
        model = BlogNewsletter
        fields = [
            "id",
            "title",
            "subject",
            "content",
            "template",
            "status",
            "sent_count",
            "open_rate",
            "click_rate",
            "scheduled_at",
            "sent_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "sent_at", "created_at", "updated_at"]

    def get_sent_count(self, obj):
        """Get number of subscribers the newsletter was sent to."""
        # This would be implemented based on your email service
        return 0

    def get_open_rate(self, obj):
        """Get newsletter open rate."""
        # This would be implemented based on your email service
        return 0.0

    def get_click_rate(self, obj):
        """Get newsletter click rate."""
        # This would be implemented based on your email service
        return 0.0


class BlogBadgeSerializer(serializers.ModelSerializer):
    """Serializer for blog badges."""

    class Meta:
        model = BlogBadge
        fields = [
            "id",
            "name",
            "description",
            "badge_type",
            "icon",
            "criteria",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class UserBlogBadgeSerializer(serializers.ModelSerializer):
    """Serializer for user blog badges."""

    badge = BlogBadgeSerializer(read_only=True)
    user_display = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = UserBlogBadge
        fields = [
            "id",
            "user",
            "user_display",
            "badge",
            "earned_at",
            "is_visible",
        ]
        read_only_fields = ["id", "user", "earned_at"]


class BlogReadingListSerializer(serializers.ModelSerializer):
    """Serializer for blog reading lists."""

    posts_count = serializers.SerializerMethodField()
    posts = serializers.SerializerMethodField()

    class Meta:
        model = BlogReadingList
        fields = [
            "id",
            "name",
            "description",
            "privacy",
            "posts_count",
            "posts",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "created_at", "updated_at"]

    def get_posts_count(self, obj):
        """Get number of posts in reading list."""
        return obj.posts.count()

    def get_posts(self, obj):
        """Get posts in reading list."""
        posts = obj.posts.filter(status=BlogPost.PostStatus.PUBLISHED)[:20]
        return BlogPostListSerializer(posts, many=True, context=self.context).data

    def create(self, validated_data):
        """Create reading list for current user."""
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class BlogViewSerializer(serializers.ModelSerializer):
    """Serializer for blog views (analytics)."""

    user_display = serializers.CharField(source="user.get_full_name", read_only=True)
    session_duration = serializers.SerializerMethodField()

    class Meta:
        model = BlogView
        fields = [
            "id",
            "user",
            "user_display",
            "ip_address",
            "user_agent",
            "referrer",
            "session_duration",
            "viewed_at",
        ]
        read_only_fields = ["id", "user", "viewed_at"]

    def get_session_duration(self, obj):
        """Get session duration in readable format."""
        if obj.session_duration:
            minutes = obj.session_duration // 60
            seconds = obj.session_duration % 60
            return f"{minutes}m {seconds}s"
        return "0s"


# Specialized serializers for different use cases


class BlogPostSitemapSerializer(serializers.ModelSerializer):
    """Lightweight serializer for sitemap generation."""

    class Meta:
        model = BlogPost
        fields = ["slug", "updated_at", "published_at"]


class BlogPostSearchSerializer(serializers.ModelSerializer):
    """Serializer optimized for search results."""

    author_display = serializers.CharField(
        source="author.get_full_name", read_only=True
    )
    categories = serializers.StringRelatedField(many=True)
    tags = serializers.StringRelatedField(many=True)
    excerpt = serializers.SerializerMethodField()
    highlight = serializers.SerializerMethodField()

    class Meta:
        model = BlogPost
        fields = [
            "id",
            "title",
            "slug",
            "excerpt",
            "author_display",
            "categories",
            "tags",
            "published_at",
            "highlight",
        ]

    def get_excerpt(self, obj):
        """Get search excerpt."""
        from django.utils.html import strip_tags

        content = strip_tags(obj.content)
        return content[:150] + "..." if len(content) > 150 else content

    def get_highlight(self, obj):
        """Get search highlights (would be populated by search engine)."""
        return getattr(obj, "_highlight", {})


class BlogCategoryStatsSerializer(serializers.ModelSerializer):
    """Serializer for category statistics."""

    posts_count = serializers.SerializerMethodField()
    recent_posts_count = serializers.SerializerMethodField()
    trending_score = serializers.SerializerMethodField()

    class Meta:
        model = BlogCategory
        fields = [
            "id",
            "name",
            "slug",
            "posts_count",
            "recent_posts_count",
            "trending_score",
        ]

    def get_posts_count(self, obj):
        """Get total posts in category."""
        return obj.get_posts_count()

    def get_recent_posts_count(self, obj):
        """Get posts in last 7 days."""
        return BlogPost.objects.filter(
            categories=obj,
            status=BlogPost.PostStatus.PUBLISHED,
            created_at__gte=timezone.now() - timedelta(days=7),
        ).count()

    def get_trending_score(self, obj):
        """Calculate trending score for category."""
        recent_posts = self.get_recent_posts_count(obj)
        total_posts = self.get_posts_count(obj)
        if total_posts == 0:
            return 0
        return (recent_posts / total_posts) * 100


class BlogTagStatsSerializer(serializers.ModelSerializer):
    """Serializer for tag statistics."""

    trending_score = serializers.SerializerMethodField()
    recent_usage = serializers.SerializerMethodField()

    class Meta:
        model = BlogTag
        fields = [
            "id",
            "name",
            "slug",
            "usage_count",
            "trending_score",
            "recent_usage",
        ]

    def get_trending_score(self, obj):
        """Calculate trending score."""
        return BlogTagSerializer().get_trending_score(obj)

    def get_recent_usage(self, obj):
        """Get recent usage count."""
        return BlogPost.objects.filter(
            tags=obj,
            status=BlogPost.PostStatus.PUBLISHED,
            created_at__gte=timezone.now() - timedelta(days=7),
        ).count()


class BlogPostModerateSerializer(serializers.ModelSerializer):
    """Serializer for post moderation actions."""

    moderation_reason = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = BlogPost
        fields = ["status", "is_featured", "moderation_reason"]

    def update(self, instance, validated_data):
        """Update post with moderation action."""
        moderation_reason = validated_data.pop("moderation_reason", "")

        # Log moderation action
        BlogModerationLog.objects.create(
            moderator=self.context["request"].user,
            action_type=(
                BlogModerationLog.ActionType.APPROVE
                if validated_data.get("status") == BlogPost.PostStatus.PUBLISHED
                else BlogModerationLog.ActionType.REJECT
            ),
            content_object=instance,
            description=moderation_reason
            or f"Post {validated_data.get('status', 'moderated')}",
            ip_address=self.context["request"].META.get("REMOTE_ADDR"),
            user_agent=self.context["request"].META.get("HTTP_USER_AGENT", ""),
        )

        return super().update(instance, validated_data)


class BlogCommentModerateSerializer(serializers.ModelSerializer):
    """Serializer for comment moderation actions."""

    moderation_reason = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = BlogComment
        fields = ["status", "moderation_reason"]

    def update(self, instance, validated_data):
        """Update comment with moderation action."""
        moderation_reason = validated_data.pop("moderation_reason", "")

        # Log moderation action
        BlogModerationLog.objects.create(
            moderator=self.context["request"].user,
            action_type=(
                BlogModerationLog.ActionType.APPROVE
                if validated_data.get("status") == BlogComment.CommentStatus.APPROVED
                else BlogModerationLog.ActionType.REJECT
            ),
            content_object=instance,
            description=moderation_reason
            or f"Comment {validated_data.get('status', 'moderated')}",
            ip_address=self.context["request"].META.get("REMOTE_ADDR"),
            user_agent=self.context["request"].META.get("HTTP_USER_AGENT", ""),
        )

        return super().update(instance, validated_data)


# Bulk operation serializers


class BulkPostActionSerializer(serializers.Serializer):
    """Serializer for bulk post actions."""

    post_ids = serializers.ListField(
        child=serializers.IntegerField(), min_length=1, max_length=100
    )
    action = serializers.ChoiceField(
        choices=[
            ("publish", "Publish"),
            ("unpublish", "Unpublish"),
            ("feature", "Feature"),
            ("unfeature", "Unfeature"),
            ("delete", "Delete"),
        ]
    )
    reason = serializers.CharField(required=False, allow_blank=True)

    def validate_post_ids(self, value):
        """Validate that all post IDs exist."""
        existing_ids = BlogPost.objects.filter(id__in=value).values_list(
            "id", flat=True
        )
        invalid_ids = set(value) - set(existing_ids)
        if invalid_ids:
            raise ValidationError(f"Invalid post IDs: {list(invalid_ids)}")
        return value


class BulkCommentActionSerializer(serializers.Serializer):
    """Serializer for bulk comment actions."""

    comment_ids = serializers.ListField(
        child=serializers.IntegerField(), min_length=1, max_length=100
    )
    action = serializers.ChoiceField(
        choices=[
            ("approve", "Approve"),
            ("reject", "Reject"),
            ("spam", "Mark as Spam"),
            ("delete", "Delete"),
        ]
    )
    reason = serializers.CharField(required=False, allow_blank=True)

    def validate_comment_ids(self, value):
        """Validate that all comment IDs exist."""
        existing_ids = BlogComment.objects.filter(id__in=value).values_list(
            "id", flat=True
        )
        invalid_ids = set(value) - set(existing_ids)
        if invalid_ids:
            raise ValidationError(f"Invalid comment IDs: {list(invalid_ids)}")
        return value


# Dashboard serializers


class BlogDashboardStatsSerializer(serializers.Serializer):
    """Serializer for blog dashboard statistics."""

    total_posts = serializers.IntegerField()
    published_posts = serializers.IntegerField()
    draft_posts = serializers.IntegerField()
    total_comments = serializers.IntegerField()
    pending_comments = serializers.IntegerField()
    total_views = serializers.IntegerField()
    unique_visitors = serializers.IntegerField()
    popular_posts = BlogPostListSerializer(many=True)
    recent_posts = BlogPostListSerializer(many=True)
    trending_tags = BlogTagSerializer(many=True)
    top_categories = BlogCategorySerializer(many=True)


class AuthorStatsSerializer(serializers.Serializer):
    """Serializer for author statistics."""

    total_posts = serializers.IntegerField()
    total_views = serializers.IntegerField()
    total_reactions = serializers.IntegerField()
    total_comments = serializers.IntegerField()
    followers_count = serializers.IntegerField()
    avg_reading_time = serializers.FloatField()
    engagement_rate = serializers.FloatField()
    top_posts = BlogPostListSerializer(many=True)
    badges = UserBlogBadgeSerializer(many=True)
