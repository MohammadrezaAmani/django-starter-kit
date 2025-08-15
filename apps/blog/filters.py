import logging
from datetime import timedelta

import django_filters
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone

from .models import (
    BlogAnalytics,
    BlogCategory,
    BlogComment,
    BlogModerationLog,
    BlogNewsletter,
    BlogPost,
    BlogReaction,
    BlogReadingList,
    BlogSeries,
    BlogSubscription,
    BlogTag,
    BlogView,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class BlogPostFilter(django_filters.FilterSet):
    """
    Comprehensive filter for blog posts with advanced filtering options.
    """

    # Basic filters
    title = django_filters.CharFilter(lookup_expr="icontains")
    slug = django_filters.CharFilter(lookup_expr="exact")
    author = django_filters.ModelChoiceFilter(queryset=User.objects.all())
    author_username = django_filters.CharFilter(
        field_name="author__username", lookup_expr="icontains"
    )
    author_name = django_filters.CharFilter(method="filter_by_author_name")

    # Status and visibility filters
    status = django_filters.ChoiceFilter(choices=BlogPost.PostStatus.choices)
    visibility = django_filters.ChoiceFilter(choices=BlogPost.Visibility.choices)
    post_type = django_filters.ChoiceFilter(choices=BlogPost.PostType.choices)
    content_format = django_filters.ChoiceFilter(choices=BlogPost.ContentFormat.choices)

    # Boolean filters
    is_featured = django_filters.BooleanFilter()
    is_trending = django_filters.BooleanFilter()
    allow_comments = django_filters.BooleanFilter()
    is_commentable = django_filters.BooleanFilter()

    # Category and tag filters
    categories = django_filters.ModelMultipleChoiceFilter(
        queryset=BlogCategory.objects.filter(is_active=True),
        conjoined=False,  # OR logic
    )
    category_slug = django_filters.CharFilter(field_name="categories__slug")
    tags = django_filters.ModelMultipleChoiceFilter(
        queryset=BlogTag.objects.all(),
        conjoined=False,  # OR logic
    )
    tag_slug = django_filters.CharFilter(field_name="tags__slug")

    # Date filters
    created_at = django_filters.DateTimeFromToRangeFilter()
    updated_at = django_filters.DateTimeFromToRangeFilter()
    published_at = django_filters.DateTimeFromToRangeFilter()

    # Date shortcuts
    created_today = django_filters.BooleanFilter(method="filter_created_today")
    created_this_week = django_filters.BooleanFilter(method="filter_created_this_week")
    created_this_month = django_filters.BooleanFilter(
        method="filter_created_this_month"
    )
    published_today = django_filters.BooleanFilter(method="filter_published_today")
    published_this_week = django_filters.BooleanFilter(
        method="filter_published_this_week"
    )
    published_this_month = django_filters.BooleanFilter(
        method="filter_published_this_month"
    )

    # Numeric filters
    reading_time = django_filters.RangeFilter()
    reading_time_min = django_filters.NumberFilter(
        field_name="reading_time", lookup_expr="gte"
    )
    reading_time_max = django_filters.NumberFilter(
        field_name="reading_time", lookup_expr="lte"
    )

    # Engagement filters
    views_count = django_filters.RangeFilter()
    views_count_min = django_filters.NumberFilter(
        field_name="views_count", lookup_expr="gte"
    )
    views_count_max = django_filters.NumberFilter(
        field_name="views_count", lookup_expr="lte"
    )
    reactions_count = django_filters.RangeFilter()
    reactions_count_min = django_filters.NumberFilter(
        field_name="reactions_count", lookup_expr="gte"
    )
    reactions_count_max = django_filters.NumberFilter(
        field_name="reactions_count", lookup_expr="lte"
    )
    comments_count = django_filters.RangeFilter()
    comments_count_min = django_filters.NumberFilter(
        field_name="comments_count", lookup_expr="gte"
    )
    comments_count_max = django_filters.NumberFilter(
        field_name="comments_count", lookup_expr="lte"
    )

    # Advanced filters
    has_featured_image = django_filters.BooleanFilter(
        method="filter_has_featured_image"
    )
    has_attachments = django_filters.BooleanFilter(method="filter_has_attachments")
    has_comments = django_filters.BooleanFilter(method="filter_has_comments")
    has_reactions = django_filters.BooleanFilter(method="filter_has_reactions")

    # Series filter
    series = django_filters.ModelChoiceFilter(
        queryset=BlogSeries.objects.filter(is_active=True),
        field_name="series_posts__series",
    )

    # Search filters
    search = django_filters.CharFilter(method="filter_search")
    content_search = django_filters.CharFilter(
        field_name="content", lookup_expr="icontains"
    )
    excerpt_search = django_filters.CharFilter(
        field_name="excerpt", lookup_expr="icontains"
    )

    # Ordering filters
    order_by_popularity = django_filters.BooleanFilter(
        method="filter_order_by_popularity"
    )
    order_by_engagement = django_filters.BooleanFilter(
        method="filter_order_by_engagement"
    )
    order_by_trending = django_filters.BooleanFilter(method="filter_order_by_trending")

    class Meta:
        model = BlogPost
        fields = [
            "title",
            "slug",
            "author",
            "status",
            "visibility",
            "post_type",
            "content_format",
            "is_featured",
            "is_trending",
            "allow_comments",
            "categories",
            "tags",
            "created_at",
            "updated_at",
            "published_at",
        ]

    def filter_by_author_name(self, queryset, name, value):
        """Filter by author's full name."""
        return queryset.filter(
            Q(author__first_name__icontains=value)
            | Q(author__last_name__icontains=value)
        )

    def filter_created_today(self, queryset, name, value):
        """Filter posts created today."""
        if value:
            today = timezone.now().date()
            return queryset.filter(created_at__date=today)
        return queryset

    def filter_created_this_week(self, queryset, name, value):
        """Filter posts created this week."""
        if value:
            week_ago = timezone.now() - timedelta(days=7)
            return queryset.filter(created_at__gte=week_ago)
        return queryset

    def filter_created_this_month(self, queryset, name, value):
        """Filter posts created this month."""
        if value:
            month_ago = timezone.now() - timedelta(days=30)
            return queryset.filter(created_at__gte=month_ago)
        return queryset

    def filter_published_today(self, queryset, name, value):
        """Filter posts published today."""
        if value:
            today = timezone.now().date()
            return queryset.filter(published_at__date=today)
        return queryset

    def filter_published_this_week(self, queryset, name, value):
        """Filter posts published this week."""
        if value:
            week_ago = timezone.now() - timedelta(days=7)
            return queryset.filter(published_at__gte=week_ago)
        return queryset

    def filter_published_this_month(self, queryset, name, value):
        """Filter posts published this month."""
        if value:
            month_ago = timezone.now() - timedelta(days=30)
            return queryset.filter(published_at__gte=month_ago)
        return queryset

    def filter_has_featured_image(self, queryset, name, value):
        """Filter posts with/without featured image."""
        if value:
            return queryset.exclude(featured_image="")
        else:
            return queryset.filter(featured_image="")

    def filter_has_attachments(self, queryset, name, value):
        """Filter posts with/without attachments."""
        if value:
            return queryset.filter(attachments__isnull=False).distinct()
        else:
            return queryset.filter(attachments__isnull=True)

    def filter_has_comments(self, queryset, name, value):
        """Filter posts with/without comments."""
        if value:
            return queryset.filter(comments__isnull=False).distinct()
        else:
            return queryset.filter(comments__isnull=True)

    def filter_has_reactions(self, queryset, name, value):
        """Filter posts with/without reactions."""
        if value:
            return queryset.filter(reactions__isnull=False).distinct()
        else:
            return queryset.filter(reactions__isnull=True)

    def filter_search(self, queryset, name, value):
        """Advanced search across multiple fields."""
        return queryset.filter(
            Q(title__icontains=value)
            | Q(content__icontains=value)
            | Q(excerpt__icontains=value)
            | Q(tags__name__icontains=value)
            | Q(categories__name__icontains=value)
            | Q(author__first_name__icontains=value)
            | Q(author__last_name__icontains=value)
        ).distinct()

    def filter_order_by_popularity(self, queryset, name, value):
        """Order by popularity (views count)."""
        if value:
            return queryset.order_by("-views_count", "-reactions_count")
        return queryset

    def filter_order_by_engagement(self, queryset, name, value):
        """Order by engagement (reactions + comments)."""
        if value:
            return queryset.annotate(
                engagement_score=Count("reactions") + Count("comments")
            ).order_by("-engagement_score")
        return queryset

    def filter_order_by_trending(self, queryset, name, value):
        """Order by trending score."""
        if value:
            # Recent posts with high engagement
            week_ago = timezone.now() - timedelta(days=7)
            return (
                queryset.filter(published_at__gte=week_ago)
                .annotate(
                    trending_score=(
                        Count("views") + Count("reactions") * 2 + Count("comments") * 3
                    )
                )
                .order_by("-trending_score")
            )
        return queryset


class BlogCategoryFilter(django_filters.FilterSet):
    """Filter for blog categories."""

    name = django_filters.CharFilter(lookup_expr="icontains")
    slug = django_filters.CharFilter(lookup_expr="exact")
    description = django_filters.CharFilter(lookup_expr="icontains")
    is_active = django_filters.BooleanFilter()
    parent = django_filters.ModelChoiceFilter(
        queryset=BlogCategory.objects.filter(is_active=True)
    )
    level = django_filters.NumberFilter()

    # Date filters
    created_at = django_filters.DateTimeFromToRangeFilter()
    updated_at = django_filters.DateTimeFromToRangeFilter()

    # Advanced filters
    has_children = django_filters.BooleanFilter(method="filter_has_children")
    is_root = django_filters.BooleanFilter(method="filter_is_root")
    posts_count_min = django_filters.NumberFilter(method="filter_posts_count_min")
    posts_count_max = django_filters.NumberFilter(method="filter_posts_count_max")

    class Meta:
        model = BlogCategory
        fields = ["name", "slug", "is_active", "parent", "level"]

    def filter_has_children(self, queryset, name, value):
        """Filter categories with/without children."""
        if value:
            return queryset.filter(children__isnull=False).distinct()
        else:
            return queryset.filter(children__isnull=True)

    def filter_is_root(self, queryset, name, value):
        """Filter root categories (no parent)."""
        if value:
            return queryset.filter(parent__isnull=True)
        else:
            return queryset.filter(parent__isnull=False)

    def filter_posts_count_min(self, queryset, name, value):
        """Filter categories with minimum posts count."""
        return queryset.annotate(posts_count=Count("blogpost")).filter(
            posts_count__gte=value
        )

    def filter_posts_count_max(self, queryset, name, value):
        """Filter categories with maximum posts count."""
        return queryset.annotate(posts_count=Count("blogpost")).filter(
            posts_count__lte=value
        )


class BlogTagFilter(django_filters.FilterSet):
    """Filter for blog tags."""

    name = django_filters.CharFilter(lookup_expr="icontains")
    slug = django_filters.CharFilter(lookup_expr="exact")
    description = django_filters.CharFilter(lookup_expr="icontains")
    is_featured = django_filters.BooleanFilter()

    # Usage filters
    usage_count = django_filters.RangeFilter()
    usage_count_min = django_filters.NumberFilter(
        field_name="usage_count", lookup_expr="gte"
    )
    usage_count_max = django_filters.NumberFilter(
        field_name="usage_count", lookup_expr="lte"
    )

    # Date filters
    created_at = django_filters.DateTimeFromToRangeFilter()
    updated_at = django_filters.DateTimeFromToRangeFilter()

    # Advanced filters
    is_trending = django_filters.BooleanFilter(method="filter_is_trending")
    created_by = django_filters.ModelChoiceFilter(queryset=User.objects.all())

    class Meta:
        model = BlogTag
        fields = ["name", "slug", "is_featured", "usage_count", "created_by"]

    def filter_is_trending(self, queryset, name, value):
        """Filter trending tags (used in recent posts)."""
        if value:
            week_ago = timezone.now() - timedelta(days=7)
            return queryset.filter(
                blogpost__created_at__gte=week_ago,
                blogpost__status=BlogPost.PostStatus.PUBLISHED,
            ).distinct()
        return queryset


class BlogCommentFilter(django_filters.FilterSet):
    """Filter for blog comments."""

    content = django_filters.CharFilter(lookup_expr="icontains")
    author = django_filters.ModelChoiceFilter(queryset=User.objects.all())
    author_username = django_filters.CharFilter(
        field_name="author__username", lookup_expr="icontains"
    )
    post = django_filters.ModelChoiceFilter(queryset=BlogPost.objects.all())
    post_slug = django_filters.CharFilter(field_name="post__slug")
    parent = django_filters.ModelChoiceFilter(queryset=BlogComment.objects.all())
    status = django_filters.ChoiceFilter(choices=BlogComment.CommentStatus.choices)
    is_pinned = django_filters.BooleanFilter()

    # Date filters
    created_at = django_filters.DateTimeFromToRangeFilter()
    updated_at = django_filters.DateTimeFromToRangeFilter()

    # Advanced filters
    is_top_level = django_filters.BooleanFilter(method="filter_is_top_level")
    is_reply = django_filters.BooleanFilter(method="filter_is_reply")
    depth = django_filters.NumberFilter(method="filter_by_depth")
    depth_min = django_filters.NumberFilter(method="filter_depth_min")
    depth_max = django_filters.NumberFilter(method="filter_depth_max")

    class Meta:
        model = BlogComment
        fields = ["author", "post", "parent", "status", "is_pinned"]

    def filter_is_top_level(self, queryset, name, value):
        """Filter top-level comments (no parent)."""
        if value:
            return queryset.filter(parent__isnull=True)
        else:
            return queryset.filter(parent__isnull=False)

    def filter_is_reply(self, queryset, name, value):
        """Filter reply comments (has parent)."""
        if value:
            return queryset.filter(parent__isnull=False)
        else:
            return queryset.filter(parent__isnull=True)

    def filter_by_depth(self, queryset, name, value):
        """Filter comments by specific depth."""
        # This would require implementing get_depth method or using tree structure
        return queryset

    def filter_depth_min(self, queryset, name, value):
        """Filter comments with minimum depth."""
        # Implementation depends on how depth is calculated
        return queryset

    def filter_depth_max(self, queryset, name, value):
        """Filter comments with maximum depth."""
        # Implementation depends on how depth is calculated
        return queryset


class BlogSeriesFilter(django_filters.FilterSet):
    """Filter for blog series."""

    title = django_filters.CharFilter(lookup_expr="icontains")
    slug = django_filters.CharFilter(lookup_expr="exact")
    description = django_filters.CharFilter(lookup_expr="icontains")
    author = django_filters.ModelChoiceFilter(queryset=User.objects.all())
    author_username = django_filters.CharFilter(
        field_name="author__username", lookup_expr="icontains"
    )
    is_active = django_filters.BooleanFilter()

    # Date filters
    created_at = django_filters.DateTimeFromToRangeFilter()
    updated_at = django_filters.DateTimeFromToRangeFilter()

    # Advanced filters
    posts_count_min = django_filters.NumberFilter(method="filter_posts_count_min")
    posts_count_max = django_filters.NumberFilter(method="filter_posts_count_max")
    has_cover_image = django_filters.BooleanFilter(method="filter_has_cover_image")

    class Meta:
        model = BlogSeries
        fields = ["title", "slug", "author", "is_active"]

    def filter_posts_count_min(self, queryset, name, value):
        """Filter series with minimum posts count."""
        return queryset.annotate(posts_count=Count("posts")).filter(
            posts_count__gte=value
        )

    def filter_posts_count_max(self, queryset, name, value):
        """Filter series with maximum posts count."""
        return queryset.annotate(posts_count=Count("posts")).filter(
            posts_count__lte=value
        )

    def filter_has_cover_image(self, queryset, name, value):
        """Filter series with/without cover image."""
        if value:
            return queryset.exclude(cover_image="")
        else:
            return queryset.filter(cover_image="")


class BlogAnalyticsFilter(django_filters.FilterSet):
    """Filter for blog analytics."""

    post = django_filters.ModelChoiceFilter(queryset=BlogPost.objects.all())
    post_slug = django_filters.CharFilter(field_name="post__slug")
    post_author = django_filters.ModelChoiceFilter(
        queryset=User.objects.all(), field_name="post__author"
    )

    # Numeric filters
    views_count = django_filters.RangeFilter()
    views_count_min = django_filters.NumberFilter(
        field_name="views_count", lookup_expr="gte"
    )
    views_count_max = django_filters.NumberFilter(
        field_name="views_count", lookup_expr="lte"
    )

    unique_views_count = django_filters.RangeFilter()
    unique_views_count_min = django_filters.NumberFilter(
        field_name="unique_views_count", lookup_expr="gte"
    )
    unique_views_count_max = django_filters.NumberFilter(
        field_name="unique_views_count", lookup_expr="lte"
    )

    shares_count = django_filters.RangeFilter()
    shares_count_min = django_filters.NumberFilter(
        field_name="shares_count", lookup_expr="gte"
    )
    shares_count_max = django_filters.NumberFilter(
        field_name="shares_count", lookup_expr="lte"
    )

    time_spent_average = django_filters.RangeFilter()
    time_spent_average_min = django_filters.NumberFilter(
        field_name="time_spent_average", lookup_expr="gte"
    )
    time_spent_average_max = django_filters.NumberFilter(
        field_name="time_spent_average", lookup_expr="lte"
    )

    # Date filters
    last_updated = django_filters.DateTimeFromToRangeFilter()

    # Advanced filters
    high_engagement = django_filters.BooleanFilter(method="filter_high_engagement")
    low_bounce_rate = django_filters.BooleanFilter(method="filter_low_bounce_rate")

    class Meta:
        model = BlogAnalytics
        fields = ["post", "views_count", "unique_views_count", "shares_count"]

    def filter_high_engagement(self, queryset, name, value):
        """Filter posts with high engagement rate."""
        if value:
            # Define high engagement as > 10%
            return (
                queryset.filter(views_count__gt=0)
                .annotate(
                    engagement_rate=(Count("post__reactions") + Count("post__comments"))
                    * 100.0
                    / F("views_count")
                )
                .filter(engagement_rate__gt=10)
            )
        return queryset

    def filter_low_bounce_rate(self, queryset, name, value):
        """Filter posts with low bounce rate."""
        if value:
            # Define low bounce rate as < 70%
            return queryset.filter(time_spent_average__gt=30)  # More than 30 seconds
        return queryset


class BlogViewFilter(django_filters.FilterSet):
    """Filter for blog views."""

    post = django_filters.ModelChoiceFilter(queryset=BlogPost.objects.all())
    post_slug = django_filters.CharFilter(field_name="post__slug")
    user = django_filters.ModelChoiceFilter(queryset=User.objects.all())
    user_username = django_filters.CharFilter(
        field_name="user__username", lookup_expr="icontains"
    )
    ip_address = django_filters.CharFilter(lookup_expr="exact")

    # Date filters
    viewed_at = django_filters.DateTimeFromToRangeFilter()
    viewed_today = django_filters.BooleanFilter(method="filter_viewed_today")
    viewed_this_week = django_filters.BooleanFilter(method="filter_viewed_this_week")
    viewed_this_month = django_filters.BooleanFilter(method="filter_viewed_this_month")

    # Advanced filters
    session_duration = django_filters.RangeFilter()
    session_duration_min = django_filters.NumberFilter(
        field_name="session_duration", lookup_expr="gte"
    )
    session_duration_max = django_filters.NumberFilter(
        field_name="session_duration", lookup_expr="lte"
    )

    has_referrer = django_filters.BooleanFilter(method="filter_has_referrer")
    referrer_domain = django_filters.CharFilter(method="filter_referrer_domain")

    class Meta:
        model = BlogView
        fields = ["post", "user", "ip_address", "viewed_at"]

    def filter_viewed_today(self, queryset, name, value):
        """Filter views from today."""
        if value:
            today = timezone.now().date()
            return queryset.filter(viewed_at__date=today)
        return queryset

    def filter_viewed_this_week(self, queryset, name, value):
        """Filter views from this week."""
        if value:
            week_ago = timezone.now() - timedelta(days=7)
            return queryset.filter(viewed_at__gte=week_ago)
        return queryset

    def filter_viewed_this_month(self, queryset, name, value):
        """Filter views from this month."""
        if value:
            month_ago = timezone.now() - timedelta(days=30)
            return queryset.filter(viewed_at__gte=month_ago)
        return queryset

    def filter_has_referrer(self, queryset, name, value):
        """Filter views with/without referrer."""
        if value:
            return queryset.exclude(referrer="")
        else:
            return queryset.filter(referrer="")

    def filter_referrer_domain(self, queryset, name, value):
        """Filter views by referrer domain."""
        return queryset.filter(referrer__icontains=value)


class BlogReactionFilter(django_filters.FilterSet):
    """Filter for blog reactions."""

    post = django_filters.ModelChoiceFilter(queryset=BlogPost.objects.all())
    post_slug = django_filters.CharFilter(field_name="post__slug")
    user = django_filters.ModelChoiceFilter(queryset=User.objects.all())
    user_username = django_filters.CharFilter(
        field_name="user__username", lookup_expr="icontains"
    )
    reaction_type = django_filters.ChoiceFilter(
        choices=BlogReaction.ReactionType.choices
    )

    # Date filters
    created_at = django_filters.DateTimeFromToRangeFilter()
    created_today = django_filters.BooleanFilter(method="filter_created_today")
    created_this_week = django_filters.BooleanFilter(method="filter_created_this_week")
    created_this_month = django_filters.BooleanFilter(
        method="filter_created_this_month"
    )

    class Meta:
        model = BlogReaction
        fields = ["post", "user", "reaction_type", "created_at"]

    def filter_created_today(self, queryset, name, value):
        """Filter reactions from today."""
        if value:
            today = timezone.now().date()
            return queryset.filter(created_at__date=today)
        return queryset

    def filter_created_this_week(self, queryset, name, value):
        """Filter reactions from this week."""
        if value:
            week_ago = timezone.now() - timedelta(days=7)
            return queryset.filter(created_at__gte=week_ago)
        return queryset

    def filter_created_this_month(self, queryset, name, value):
        """Filter reactions from this month."""
        if value:
            month_ago = timezone.now() - timedelta(days=30)
            return queryset.filter(created_at__gte=month_ago)
        return queryset


class BlogSubscriptionFilter(django_filters.FilterSet):
    """Filter for blog subscriptions."""

    user = django_filters.ModelChoiceFilter(queryset=User.objects.all())
    user_username = django_filters.CharFilter(
        field_name="user__username", lookup_expr="icontains"
    )
    subscription_type = django_filters.ChoiceFilter(
        choices=BlogSubscription.SubscriptionType.choices
    )
    notification_frequency = django_filters.ChoiceFilter(
        choices=BlogSubscription.NotificationFrequency.choices
    )
    is_active = django_filters.BooleanFilter()

    # Date filters
    subscribed_at = django_filters.DateTimeFromToRangeFilter()
    subscribed_today = django_filters.BooleanFilter(method="filter_subscribed_today")
    subscribed_this_week = django_filters.BooleanFilter(
        method="filter_subscribed_this_week"
    )
    subscribed_this_month = django_filters.BooleanFilter(
        method="filter_subscribed_this_month"
    )

    class Meta:
        model = BlogSubscription
        fields = ["user", "subscription_type", "notification_frequency", "is_active"]

    def filter_subscribed_today(self, queryset, name, value):
        """Filter subscriptions from today."""
        if value:
            today = timezone.now().date()
            return queryset.filter(subscribed_at__date=today)
        return queryset

    def filter_subscribed_this_week(self, queryset, name, value):
        """Filter subscriptions from this week."""
        if value:
            week_ago = timezone.now() - timedelta(days=7)
            return queryset.filter(subscribed_at__gte=week_ago)
        return queryset

    def filter_subscribed_this_month(self, queryset, name, value):
        """Filter subscriptions from this month."""
        if value:
            month_ago = timezone.now() - timedelta(days=30)
            return queryset.filter(subscribed_at__gte=month_ago)
        return queryset


class BlogModerationLogFilter(django_filters.FilterSet):
    """Filter for blog moderation logs."""

    moderator = django_filters.ModelChoiceFilter(queryset=User.objects.all())
    moderator_username = django_filters.CharFilter(
        field_name="moderator__username", lookup_expr="icontains"
    )
    action_type = django_filters.ChoiceFilter(
        choices=BlogModerationLog.ActionType.choices
    )
    description = django_filters.CharFilter(lookup_expr="icontains")
    ip_address = django_filters.CharFilter(lookup_expr="exact")

    # Date filters
    created_at = django_filters.DateTimeFromToRangeFilter()
    created_today = django_filters.BooleanFilter(method="filter_created_today")
    created_this_week = django_filters.BooleanFilter(method="filter_created_this_week")
    created_this_month = django_filters.BooleanFilter(
        method="filter_created_this_month"
    )

    # Content type filters
    content_type = django_filters.CharFilter(field_name="content_type__model")

    class Meta:
        model = BlogModerationLog
        fields = ["moderator", "action_type", "content_type", "created_at"]

    def filter_created_today(self, queryset, name, value):
        """Filter logs from today."""
        if value:
            today = timezone.now().date()
            return queryset.filter(created_at__date=today)
        return queryset

    def filter_created_this_week(self, queryset, name, value):
        """Filter logs from this week."""
        if value:
            week_ago = timezone.now() - timedelta(days=7)
            return queryset.filter(created_at__gte=week_ago)
        return queryset

    def filter_created_this_month(self, queryset, name, value):
        """Filter logs from this month."""
        if value:
            month_ago = timezone.now() - timedelta(days=30)
            return queryset.filter(created_at__gte=month_ago)
        return queryset


class BlogNewsletterFilter(django_filters.FilterSet):
    """Filter for blog newsletters."""

    title = django_filters.CharFilter(lookup_expr="icontains")
    subject = django_filters.CharFilter(lookup_expr="icontains")
    status = django_filters.ChoiceFilter(
        choices=BlogNewsletter.NewsletterStatus.choices
    )

    # Date filters
    scheduled_at = django_filters.DateTimeFromToRangeFilter()
    sent_at = django_filters.DateTimeFromToRangeFilter()
    created_at = django_filters.DateTimeFromToRangeFilter()
    updated_at = django_filters.DateTimeFromToRangeFilter()

    # Advanced filters
    is_scheduled = django_filters.BooleanFilter(method="filter_is_scheduled")
    is_sent = django_filters.BooleanFilter(method="filter_is_sent")

    class Meta:
        model = BlogNewsletter
        fields = ["title", "subject", "status", "scheduled_at", "sent_at"]

    def filter_is_scheduled(self, queryset, name, value):
        """Filter newsletters that are scheduled."""
        if value:
            return queryset.exclude(scheduled_at__isnull=True)
        else:
            return queryset.filter(scheduled_at__isnull=True)

    def filter_is_sent(self, queryset, name, value):
        """Filter newsletters that have been sent."""
        if value:
            return queryset.exclude(sent_at__isnull=True)
        else:
            return queryset.filter(sent_at__isnull=True)


class BlogReadingListFilter(django_filters.FilterSet):
    """Filter for blog reading lists."""

    name = django_filters.CharFilter(lookup_expr="icontains")
    description = django_filters.CharFilter(lookup_expr="icontains")
    user = django_filters.ModelChoiceFilter(queryset=User.objects.all())
    user_username = django_filters.CharFilter(
        field_name="user__username", lookup_expr="icontains"
    )
    privacy = django_filters.ChoiceFilter(choices=BlogReadingList.Privacy.choices)

    # Date filters
    created_at = django_filters.DateTimeFromToRangeFilter()
    updated_at = django_filters.DateTimeFromToRangeFilter()

    # Advanced filters
    posts_count_min = django_filters.NumberFilter(method="filter_posts_count_min")
    posts_count_max = django_filters.NumberFilter(method="filter_posts_count_max")
    has_posts = django_filters.BooleanFilter(method="filter_has_posts")

    class Meta:
        model = BlogReadingList
        fields = ["name", "user", "privacy", "created_at", "updated_at"]

    def filter_posts_count_min(self, queryset, name, value):
        """Filter reading lists with minimum posts count."""
        return queryset.annotate(posts_count=Count("posts")).filter(
            posts_count__gte=value
        )

    def filter_posts_count_max(self, queryset, name, value):
        """Filter reading lists with maximum posts count."""
        return queryset.annotate(posts_count=Count("posts")).filter(
            posts_count__lte=value
        )

    def filter_has_posts(self, queryset, name, value):
        """Filter reading lists with/without posts."""
        if value:
            return queryset.filter(posts__isnull=False).distinct()
        else:
            return queryset.filter(posts__isnull=True)


# Custom filter for date ranges
class DateRangeFilter(django_filters.Filter):
    """Custom filter for date ranges with predefined options."""

    def filter(self, qs, value):
        if not value:
            return qs

        now = timezone.now()

        if value == "today":
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=1)
        elif value == "yesterday":
            start_date = now.replace(
                hour=0, minute=0, second=0, microsecond=0
            ) - timedelta(days=1)
            end_date = start_date + timedelta(days=1)
        elif value == "this_week":
            start_date = now - timedelta(days=now.weekday())
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=7)
        elif value == "last_week":
            start_date = now - timedelta(days=now.weekday() + 7)
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=7)
        elif value == "this_month":
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if start_date.month == 12:
                end_date = start_date.replace(year=start_date.year + 1, month=1)
            else:
                end_date = start_date.replace(month=start_date.month + 1)
        elif value == "last_month":
            if now.month == 1:
                start_date = now.replace(
                    year=now.year - 1,
                    month=12,
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
            else:
                start_date = now.replace(
                    month=now.month - 1,
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
            end_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif value == "this_year":
            start_date = now.replace(
                month=1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
            end_date = start_date.replace(year=start_date.year + 1)
        elif value == "last_year":
            start_date = now.replace(
                year=now.year - 1,
                month=1,
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            end_date = now.replace(
                month=1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
        else:
            return qs

        return qs.filter(
            **{
                f"{self.field_name}__gte": start_date,
                f"{self.field_name}__lt": end_date,
            }
        )
