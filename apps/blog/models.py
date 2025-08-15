import hashlib
import json
import logging
import uuid
from datetime import timedelta
from decimal import Decimal

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

# from django.contrib.postgres.fields import ArrayField  # Commented out for SQLite compatibility
# from django.contrib.postgres.indexes import GinIndex  # Commented out for SQLite compatibility
from django.contrib.postgres.search import (
    SearchQuery,
    SearchRank,
    # SearchVector,
    # SearchVectorField,
)  # Commented out for SQLite compatibility
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models
from django.db.models.signals import m2m_changed, post_save, pre_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from mptt.models import MPTTModel, TreeForeignKey

logger = logging.getLogger(__name__)
User = get_user_model()


class BlogCategoryQuerySet(models.QuerySet):
    """Custom queryset for BlogCategory with useful filters."""

    def active(self):
        return self.filter(is_active=True)

    def root_categories(self):
        return self.filter(parent__isnull=True)

    def with_post_count(self):
        return self.annotate(post_count=models.Count("blog_posts"))


class BlogCategory(MPTTModel):
    """
    Hierarchical categories for blog posts with MPTT for efficient tree operations.
    Includes SEO optimization and performance features.
    """

    class Meta:
        verbose_name = _("Blog Category")
        verbose_name_plural = _("Blog Categories")
        ordering = ["tree_id", "lft"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["parent", "is_active"]),
            # GinIndex(fields=["search_vector"]),  # Commented out for SQLite compatibility
        ]
        permissions = [
            ("can_manage_categories", "Can manage blog categories"),
            ("can_view_analytics", "Can view category analytics"),
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Name"), max_length=100)
    slug = models.SlugField(_("Slug"), unique=True, max_length=120)
    description = models.TextField(_("Description"), blank=True, max_length=1000)
    parent = TreeForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        verbose_name=_("Parent Category"),
    )
    icon = models.ImageField(
        _("Icon"),
        upload_to="blog/category_icons/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "svg", "webp"])],
    )
    cover_image = models.ImageField(
        _("Cover Image"),
        upload_to="blog/category_covers/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
    )
    color = models.CharField(
        _("Color"), max_length=7, default="#6366f1", help_text="Hex color code"
    )
    seo_title = models.CharField(_("SEO Title"), max_length=60, blank=True)
    seo_description = models.CharField(_("SEO Description"), max_length=160, blank=True)
    seo_keywords = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("SEO Keywords"),
        help_text="List of SEO keywords",
    )
    canonical_url = models.URLField(_("Canonical URL"), blank=True)
    is_active = models.BooleanField(_("Is Active"), default=True)
    is_featured = models.BooleanField(_("Is Featured"), default=False)
    sort_order = models.PositiveIntegerField(_("Sort Order"), default=0)
    post_count = models.PositiveIntegerField(_("Post Count"), default=0, editable=False)
    view_count = models.PositiveIntegerField(_("View Count"), default=0, editable=False)
    # search_vector = SearchVectorField(null=True)  # Commented out for SQLite compatibility
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_categories",
        verbose_name=_("Created By"),
    )

    objects = BlogCategoryQuerySet.as_manager()

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("blog:category_detail", kwargs={"slug": self.slug})

    def get_posts_count(self):
        """Get total posts count including subcategories."""
        return (
            self.get_descendants(include_self=True).aggregate(
                total=models.Sum("post_count")
            )["total"]
            or 0
        )

    def get_breadcrumbs(self):
        """Get category breadcrumbs."""
        return self.get_ancestors(include_self=True)


class BlogTagQuerySet(models.QuerySet):
    """Custom queryset for BlogTag."""

    def popular(self, limit=20):
        return self.order_by("-usage_count")[:limit]

    def trending(self, days=7):
        return (
            self.filter(
                blog_posts__created_at__gte=timezone.now() - timedelta(days=days)
            )
            .annotate(recent_usage=models.Count("blog_posts"))
            .order_by("-recent_usage")
        )


class BlogTag(models.Model):
    """
    Tags for blog posts with advanced features like synonyms and trending analysis.
    """

    class Meta:
        verbose_name = _("Blog Tag")
        verbose_name_plural = _("Blog Tags")
        ordering = ["-usage_count", "name"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["-usage_count"]),
            # GinIndex(fields=["search_vector"]),  # Commented out for SQLite compatibility
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Name"), max_length=50, unique=True)
    slug = models.SlugField(_("Slug"), unique=True, max_length=60)
    description = models.TextField(_("Description"), blank=True, max_length=500)
    synonyms = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Synonyms"),
        help_text="List of tag synonyms",
    )
    color = models.CharField(
        _("Color"), max_length=7, default="#6b7280", help_text="Hex color code"
    )
    usage_count = models.PositiveIntegerField(
        _("Usage Count"), default=0, editable=False
    )
    trending_score = models.FloatField(_("Trending Score"), default=0.0, editable=False)
    is_featured = models.BooleanField(_("Is Featured"), default=False)
    # search_vector = SearchVectorField(null=True)  # Commented out for SQLite compatibility
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_tags",
        verbose_name=_("Created By"),
    )

    objects = BlogTagQuerySet.as_manager()

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("blog:tag_detail", kwargs={"slug": self.slug})


class BlogPostQuerySet(models.QuerySet):
    """Custom queryset for BlogPost with advanced filtering and search."""

    def published(self):
        return self.filter(
            status=BlogPost.PostStatus.PUBLISHED, publish_date__lte=timezone.now()
        )

    def featured(self):
        return self.filter(is_featured=True)

    def by_author(self, user):
        return self.filter(models.Q(author=user) | models.Q(co_authors=user)).distinct()

    def public(self):
        return self.filter(visibility=BlogPost.Visibility.PUBLIC)

    def with_analytics(self):
        return self.select_related("analytics").prefetch_related(
            "categories", "tags", "author__userprofile"
        )

    def search(self, query):
        """Full-text search with ranking."""
        search_query = SearchQuery(query)
        return (
            self.annotate(
                search_rank=SearchRank(models.F("search_vector"), search_query)
            )
            .filter(search_vector=search_query)
            .order_by("-search_rank")
        )

    def trending(self, days=7):
        """Get trending posts based on engagement."""
        since = timezone.now() - timedelta(days=days)
        return (
            self.filter(created_at__gte=since)
            .annotate(
                engagement_score=models.F("view_count")
                + models.F("like_count") * 2
                + models.F("comment_count") * 3
                + models.F("share_count") * 5
            )
            .order_by("-engagement_score")
        )


class BlogPost(models.Model):
    """
    Ultra-advanced blog post model with Lexical content, versioning, SEO,
    monetization, and deep integrations.
    """

    class PostStatus(models.TextChoices):
        DRAFT = "draft", _("Draft")
        REVIEW = "review", _("Under Review")
        SCHEDULED = "scheduled", _("Scheduled")
        PUBLISHED = "published", _("Published")
        ARCHIVED = "archived", _("Archived")
        PRIVATE = "private", _("Private")
        DELETED = "deleted", _("Deleted")

    class Visibility(models.TextChoices):
        PUBLIC = "public", _("Public")
        SUBSCRIBERS_ONLY = "subscribers_only", _("Subscribers Only")
        PAYWALL = "paywall", _("Paywall")
        MEMBERS_ONLY = "members_only", _("Members Only")
        INTERNAL = "internal", _("Internal")
        PRIVATE = "private", _("Private")

    class ContentFormat(models.TextChoices):
        LEXICAL = "lexical", _("Lexical JSON")
        MARKDOWN = "markdown", _("Markdown")
        HTML = "html", _("HTML")
        PLAIN_TEXT = "plain_text", _("Plain Text")

    class PostType(models.TextChoices):
        ARTICLE = "article", _("Article")
        NEWS = "news", _("News")
        TUTORIAL = "tutorial", _("Tutorial")
        REVIEW = "review", _("Review")
        OPINION = "opinion", _("Opinion")
        INTERVIEW = "interview", _("Interview")
        ANNOUNCEMENT = "announcement", _("Announcement")
        CASE_STUDY = "case_study", _("Case Study")

    class Meta:
        verbose_name = _("Blog Post")
        verbose_name_plural = _("Blog Posts")
        ordering = ["-publish_date", "-created_at"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["status", "visibility"]),
            models.Index(fields=["author", "-publish_date"]),
            models.Index(fields=["-publish_date", "status"]),
            models.Index(fields=["is_featured", "-publish_date"]),
            # GinIndex(fields=["search_vector"]),  # Commented out for SQLite compatibility
            models.Index(fields=["scheduled_date"]),
            models.Index(fields=["-created_at"]),
        ]
        permissions = [
            ("can_moderate_posts", "Can moderate blog posts"),
            ("can_publish_posts", "Can publish blog posts"),
            ("can_schedule_posts", "Can schedule blog posts"),
            ("can_view_analytics", "Can view post analytics"),
            ("can_manage_monetization", "Can manage post monetization"),
        ]

    # Primary fields
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(_("Title"), max_length=300)
    slug = models.SlugField(_("Slug"), unique=True, max_length=350)
    subtitle = models.CharField(_("Subtitle"), max_length=500, blank=True)
    excerpt = models.TextField(_("Excerpt"), max_length=1000, blank=True)

    # Content fields (Lexical JSON format)
    content = models.JSONField(
        _("Content"), default=dict, help_text=_("Lexical JSON format content")
    )
    content_format = models.CharField(
        _("Content Format"),
        max_length=20,
        choices=ContentFormat.choices,
        default=ContentFormat.LEXICAL,
    )
    raw_content = models.TextField(
        _("Raw Content"),
        blank=True,
        help_text=_("Plain text version for search indexing"),
    )
    content_hash = models.CharField(
        _("Content Hash"),
        max_length=64,
        blank=True,
        help_text=_("SHA-256 hash for content integrity"),
    )

    # Author and collaboration
    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="blog_posts_authored",
        verbose_name=_("Author"),
    )
    co_authors = models.ManyToManyField(
        User,
        blank=True,
        related_name="blog_posts_coauthored",
        verbose_name=_("Co-authors"),
    )
    editor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blog_posts_edited",
        verbose_name=_("Editor"),
    )

    # Status and visibility
    status = models.CharField(
        _("Status"), max_length=20, choices=PostStatus.choices, default=PostStatus.DRAFT
    )
    visibility = models.CharField(
        _("Visibility"),
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.PUBLIC,
    )
    post_type = models.CharField(
        _("Post Type"),
        max_length=20,
        choices=PostType.choices,
        default=PostType.ARTICLE,
    )

    # Publishing
    publish_date = models.DateTimeField(_("Publish Date"), null=True, blank=True)
    scheduled_date = models.DateTimeField(_("Scheduled Date"), null=True, blank=True)
    expiry_date = models.DateTimeField(_("Expiry Date"), null=True, blank=True)

    # Categorization
    categories = models.ManyToManyField(
        BlogCategory,
        blank=True,
        related_name="blog_posts",
        verbose_name=_("Categories"),
    )
    tags = models.ManyToManyField(
        BlogTag, blank=True, related_name="blog_posts", verbose_name=_("Tags")
    )

    # Media
    featured_image = models.ImageField(
        _("Featured Image"),
        upload_to="blog/featured_images/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
    )
    featured_image_alt = models.CharField(
        _("Featured Image Alt Text"), max_length=255, blank=True
    )
    featured_video = models.URLField(_("Featured Video URL"), blank=True)

    # SEO and metadata
    seo_title = models.CharField(_("SEO Title"), max_length=60, blank=True)
    seo_description = models.CharField(_("SEO Description"), max_length=160, blank=True)
    seo_keywords = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("SEO Keywords"),
        help_text="List of SEO keywords",
    )
    canonical_url = models.URLField(_("Canonical URL"), blank=True)
    meta_robots = models.CharField(
        _("Meta Robots"),
        max_length=100,
        default="index,follow",
        help_text=_("SEO meta robots directive"),
    )
    open_graph_data = models.JSONField(
        _("Open Graph Data"),
        default=dict,
        blank=True,
        help_text=_("Social media sharing metadata"),
    )
    structured_data = models.JSONField(
        _("Structured Data"),
        default=dict,
        blank=True,
        help_text=_("JSON-LD structured data for search engines"),
    )

    # AI and automation
    ai_generated = models.BooleanField(_("AI Generated"), default=False)
    ai_metadata = models.JSONField(
        _("AI Metadata"),
        default=dict,
        blank=True,
        help_text=_("AI generation details and prompts"),
    )
    ai_suggestions = models.JSONField(
        _("AI Suggestions"),
        default=dict,
        blank=True,
        help_text=_("AI-generated suggestions for improvement"),
    )
    auto_translate = models.BooleanField(_("Auto Translate"), default=False)

    # Versioning
    version = models.PositiveIntegerField(_("Version"), default=1)
    parent_version = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revisions",
        verbose_name=_("Parent Version"),
    )
    version_notes = models.TextField(_("Version Notes"), blank=True)

    # Integrations with existing models
    linked_project = models.ForeignKey(
        "accounts.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blog_posts",
        verbose_name=_("Linked Project"),
    )
    linked_task = models.ForeignKey(
        "accounts.Task",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blog_posts",
        verbose_name=_("Linked Task"),
    )
    linked_network = models.ForeignKey(
        "accounts.Network",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blog_posts",
        verbose_name=_("Linked Network"),
    )
    linked_chat = models.ForeignKey(
        "chats.Chat",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blog_posts",
        verbose_name=_("Linked Chat"),
    )

    # Customization
    custom_template = models.CharField(
        _("Custom Template"),
        max_length=100,
        blank=True,
        help_text=_("Custom template for rendering"),
    )
    custom_css = models.TextField(_("Custom CSS"), blank=True)
    custom_js = models.TextField(_("Custom JavaScript"), blank=True)

    # A/B Testing
    ab_test_variant = models.CharField(
        _("A/B Test Variant"),
        max_length=10,
        blank=True,
        help_text=_("Variant identifier for A/B testing"),
    )
    ab_test_group = models.CharField(_("A/B Test Group"), max_length=50, blank=True)

    # Monetization
    is_premium = models.BooleanField(_("Is Premium"), default=False)
    price = models.DecimalField(
        _("Price"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    currency = models.CharField(_("Currency"), max_length=3, default="USD")
    subscription_tiers = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Subscription Tiers"),
        help_text="List of subscription tiers",
    )
    paywall_position = models.PositiveIntegerField(
        _("Paywall Position"),
        default=0,
        help_text=_("Character position where paywall appears"),
    )
    tip_enabled = models.BooleanField(_("Tips Enabled"), default=False)

    # Internationalization
    language = models.CharField(_("Language"), max_length=10, default="en")
    languages = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Languages"),
        help_text="List of supported languages",
    )
    translations = models.JSONField(
        _("Translations"),
        default=dict,
        blank=True,
        help_text=_("Translations in different languages"),
    )
    translation_parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="translation_versions",
        verbose_name=_("Translation Parent"),
    )

    # Engagement and analytics
    view_count = models.PositiveIntegerField(_("View Count"), default=0, editable=False)
    unique_view_count = models.PositiveIntegerField(
        _("Unique View Count"), default=0, editable=False
    )
    like_count = models.PositiveIntegerField(_("Like Count"), default=0, editable=False)
    dislike_count = models.PositiveIntegerField(
        _("Dislike Count"), default=0, editable=False
    )
    comment_count = models.PositiveIntegerField(
        _("Comment Count"), default=0, editable=False
    )
    share_count = models.PositiveIntegerField(
        _("Share Count"), default=0, editable=False
    )
    bookmark_count = models.PositiveIntegerField(
        _("Bookmark Count"), default=0, editable=False
    )
    download_count = models.PositiveIntegerField(
        _("Download Count"), default=0, editable=False
    )

    # Reading metrics
    reading_time = models.PositiveIntegerField(
        _("Reading Time"), default=0, help_text=_("Estimated reading time in minutes")
    )
    word_count = models.PositiveIntegerField(_("Word Count"), default=0, editable=False)
    character_count = models.PositiveIntegerField(
        _("Character Count"), default=0, editable=False
    )

    # Content quality
    quality_score = models.FloatField(
        _("Quality Score"),
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
        help_text=_("AI-calculated content quality score"),
    )
    readability_score = models.FloatField(
        _("Readability Score"), default=0.0, help_text=_("Flesch reading ease score")
    )
    seo_score = models.FloatField(
        _("SEO Score"),
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
    )

    # Moderation
    is_featured = models.BooleanField(_("Is Featured"), default=False)
    is_trending = models.BooleanField(_("Is Trending"), default=False, editable=False)
    is_editors_choice = models.BooleanField(_("Editor's Choice"), default=False)
    is_sponsored = models.BooleanField(_("Is Sponsored"), default=False)
    moderation_notes = models.TextField(_("Moderation Notes"), blank=True)
    content_warnings = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Content Warnings"),
        help_text="Content warnings for sensitive topics",
    )

    # Search and discovery
    # search_vector = SearchVectorField(null=True)  # Commented out for SQLite compatibility
    search_boost = models.FloatField(_("Search Boost"), default=1.0)
    allow_indexing = models.BooleanField(_("Allow Indexing"), default=True)
    allow_comments = models.BooleanField(_("Allow Comments"), default=True)
    allow_reactions = models.BooleanField(_("Allow Reactions"), default=True)
    allow_shares = models.BooleanField(_("Allow Shares"), default=True)

    # Timestamps
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    last_viewed_at = models.DateTimeField(_("Last Viewed At"), null=True, blank=True)
    last_modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="last_modified_posts",
        verbose_name=_("Last Modified By"),
    )

    objects = BlogPostQuerySet.as_manager()

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Generate slug if not provided
        if not self.slug:
            self.slug = slugify(self.title)

        # Ensure unique slug
        if BlogPost.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
            self.slug = f"{self.slug}-{uuid.uuid4().hex[:8]}"

        # Calculate content metrics
        if self.raw_content:
            self.word_count = len(self.raw_content.split())
            self.character_count = len(self.raw_content)
            # Estimate reading time (average 200 words per minute)
            self.reading_time = max(1, self.word_count // 200)

        # Generate content hash for published content
        if self.status == self.PostStatus.PUBLISHED and self.content:
            content_str = json.dumps(self.content, sort_keys=True)
            self.content_hash = hashlib.sha256(content_str.encode()).hexdigest()

        # Set publish date
        if self.status == self.PostStatus.PUBLISHED and not self.publish_date:
            self.publish_date = timezone.now()

        # Auto-generate SEO fields if empty
        if not self.seo_title and self.title:
            self.seo_title = self.title[:60]
        if not self.seo_description and self.excerpt:
            self.seo_description = self.excerpt[:160]

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("blog:post_detail", kwargs={"slug": self.slug})

    def get_reading_time_display(self):
        """Return human-readable reading time."""
        if self.reading_time < 1:
            return _("Less than 1 minute")
        elif self.reading_time == 1:
            return _("1 minute")
        else:
            return _("%(time)d minutes") % {"time": self.reading_time}

    def is_published(self):
        """Check if post is published and visible."""
        return (
            self.status == self.PostStatus.PUBLISHED
            and self.publish_date
            and self.publish_date <= timezone.now()
        )

    def can_be_viewed_by(self, user):
        """Check if user can view this post."""
        if not self.is_published():
            return False

        if self.visibility == self.Visibility.PUBLIC:
            return True
        elif self.visibility == self.Visibility.PRIVATE:
            return user == self.author or user in self.co_authors.all()
        elif self.visibility == self.Visibility.SUBSCRIBERS_ONLY:
            # Check if user is subscribed to author or blog
            return user.is_authenticated and hasattr(user, "blog_subscriptions")
        elif self.visibility == self.Visibility.PAYWALL:
            # Check if user has paid or has subscription
            return user.is_authenticated  # Simplified check
        elif self.visibility == self.Visibility.MEMBERS_ONLY:
            return user.is_authenticated
        elif self.visibility == self.Visibility.INTERNAL:
            return user.is_staff

        return False

    def get_engagement_score(self):
        """Calculate engagement score based on interactions."""
        return (
            self.view_count * 1
            + self.like_count * 3
            + self.comment_count * 5
            + self.share_count * 7
            + self.bookmark_count * 2
        )

    def get_related_posts(self, limit=5):
        """Get related posts based on tags and categories."""
        related = BlogPost.objects.published().exclude(pk=self.pk)

        # Filter by same tags or categories
        if self.tags.exists() or self.categories.exists():
            related = related.filter(
                models.Q(tags__in=self.tags.all())
                | models.Q(categories__in=self.categories.all())
            ).distinct()

        return related.order_by("-publish_date")[:limit]

    def increment_view_count(self, user=None, ip=None):
        """Increment view count and track unique views."""
        # Create view record
        BlogView.objects.create(
            post=self,
            user=user if user and user.is_authenticated else None,
            ip_address=ip,
        )

        # Update counts
        self.view_count = models.F("view_count") + 1
        self.save(update_fields=["view_count"])

    def notify_subscribers(self, event_type="new_post"):
        """Send notifications to subscribers."""
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"blog_post_{self.id}",
                    {
                        "type": "blog_notification",
                        "event": event_type,
                        "post_id": str(self.id),
                        "title": self.title,
                        "author": self.author.get_full_name() if self.author else "",
                    },
                )
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")


class BlogPostVersion(models.Model):
    """
    Version history for blog posts with detailed change tracking.
    """

    class Meta:
        verbose_name = _("Blog Post Version")
        verbose_name_plural = _("Blog Post Versions")
        ordering = ["-version_number"]
        unique_together = [["post", "version_number"]]
        indexes = [
            models.Index(fields=["post", "-version_number"]),
            models.Index(fields=["created_at"]),
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(
        BlogPost,
        on_delete=models.CASCADE,
        related_name="versions",
        verbose_name=_("Post"),
    )
    version_number = models.PositiveIntegerField(_("Version Number"))
    title = models.CharField(_("Title"), max_length=300)
    content = models.JSONField(_("Content"), default=dict)
    raw_content = models.TextField(_("Raw Content"), blank=True)
    changes_summary = models.TextField(_("Changes Summary"), blank=True)
    changes_diff = models.JSONField(
        _("Changes Diff"),
        default=dict,
        blank=True,
        help_text=_("Detailed diff of changes"),
    )
    editor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, verbose_name=_("Editor")
    )
    edit_reason = models.CharField(_("Edit Reason"), max_length=200, blank=True)
    is_major_edit = models.BooleanField(_("Is Major Edit"), default=False)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    def __str__(self):
        return f"{self.post.title} v{self.version_number}"

    def get_previous_version(self):
        """Get the previous version of this post."""
        return self.__class__.objects.filter(
            post=self.post, version_number__lt=self.version_number
        ).first()

    def restore(self):
        """Restore this version as the current post content."""
        self.post.content = self.content
        self.post.raw_content = self.raw_content
        self.post.title = self.title
        self.post.version = models.F("version") + 1
        self.post.save()


class BlogAttachment(models.Model):
    """
    Multimedia attachments for blog posts with advanced metadata.
    """

    class AttachmentType(models.TextChoices):
        IMAGE = "image", _("Image")
        VIDEO = "video", _("Video")
        AUDIO = "audio", _("Audio")
        DOCUMENT = "document", _("Document")
        EMBED = "embed", _("Embed")
        GALLERY = "gallery", _("Gallery")
        CODE = "code", _("Code")

    class Meta:
        verbose_name = _("Blog Attachment")
        verbose_name_plural = _("Blog Attachments")
        ordering = ["sort_order", "created_at"]
        indexes = [
            models.Index(fields=["post", "type"]),
            models.Index(fields=["created_at"]),
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(
        BlogPost,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name=_("Post"),
    )
    file = models.FileField(
        _("File"), upload_to="blog/attachments/", blank=True, null=True
    )
    url = models.URLField(_("External URL"), blank=True)
    type = models.CharField(_("Type"), max_length=20, choices=AttachmentType.choices)
    title = models.CharField(_("Title"), max_length=200, blank=True)
    description = models.TextField(_("Description"), blank=True, max_length=1000)
    alt_text = models.CharField(
        _("Alt Text"),
        max_length=255,
        blank=True,
        help_text=_("Alternative text for accessibility"),
    )
    caption = models.TextField(_("Caption"), blank=True, max_length=500)
    credit = models.CharField(_("Credit"), max_length=200, blank=True)
    copyright = models.CharField(_("Copyright"), max_length=200, blank=True)
    metadata = models.JSONField(
        _("Metadata"),
        default=dict,
        blank=True,
        help_text=_("File metadata like dimensions, duration, etc."),
    )
    size = models.PositiveIntegerField(
        _("Size"), default=0, help_text=_("File size in bytes")
    )
    mime_type = models.CharField(_("MIME Type"), max_length=100, blank=True)
    sort_order = models.PositiveIntegerField(_("Sort Order"), default=0)
    is_featured = models.BooleanField(_("Is Featured"), default=False)
    download_count = models.PositiveIntegerField(
        _("Download Count"), default=0, editable=False
    )
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_attachments",
        verbose_name=_("Uploaded By"),
    )

    def __str__(self):
        return f"{self.type.title()} - {self.title or self.file.name}"

    def save(self, *args, **kwargs):
        if self.file:
            self.size = self.file.size
            # Set MIME type based on file
            import mimetypes

            self.mime_type = mimetypes.guess_type(self.file.name)[0] or ""
        super().save(*args, **kwargs)

    def get_download_url(self):
        """Get secure download URL."""
        if self.file:
            return reverse("blog:attachment_download", kwargs={"pk": self.pk})
        return self.url


class BlogCommentQuerySet(models.QuerySet):
    """Custom queryset for BlogComment."""

    def approved(self):
        return self.filter(status=BlogComment.CommentStatus.APPROVED)

    def pending(self):
        return self.filter(status=BlogComment.CommentStatus.PENDING)

    def top_level(self):
        return self.filter(parent__isnull=True)

    def replies(self):
        return self.filter(parent__isnull=False)

    def with_replies_count(self):
        return self.annotate(replies_count=models.Count("replies"))


class BlogComment(models.Model):
    """
    Advanced comment system with threading, reactions, and moderation.
    """

    class CommentStatus(models.TextChoices):
        PENDING = "pending", _("Pending Moderation")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")
        SPAM = "spam", _("Spam")
        DELETED = "deleted", _("Deleted")

    class Meta:
        verbose_name = _("Blog Comment")
        verbose_name_plural = _("Blog Comments")
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["post", "status", "created_at"]),
            models.Index(fields=["author", "created_at"]),
            models.Index(fields=["parent", "created_at"]),
        ]
        permissions = [
            ("can_moderate_comments", "Can moderate blog comments"),
            ("can_approve_comments", "Can approve comments"),
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(
        BlogPost,
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name=_("Post"),
    )
    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="blog_comments",
        verbose_name=_("Author"),
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
        verbose_name=_("Parent Comment"),
    )
    content = models.TextField(_("Content"), max_length=5000)
    content_format = models.CharField(
        _("Content Format"),
        max_length=20,
        choices=[
            ("plain", _("Plain Text")),
            ("markdown", _("Markdown")),
            ("html", _("HTML")),
        ],
        default="plain",
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=CommentStatus.choices,
        default=CommentStatus.PENDING,
    )
    ip_address = models.GenericIPAddressField(_("IP Address"), null=True, blank=True)
    user_agent = models.TextField(_("User Agent"), blank=True)

    # Reactions and engagement
    like_count = models.PositiveIntegerField(_("Like Count"), default=0, editable=False)
    dislike_count = models.PositiveIntegerField(
        _("Dislike Count"), default=0, editable=False
    )
    reply_count = models.PositiveIntegerField(
        _("Reply Count"), default=0, editable=False
    )
    reactions = models.JSONField(
        _("Reactions"),
        default=dict,
        blank=True,
        help_text=_("Emoji reactions with counts"),
    )

    # Moderation
    is_pinned = models.BooleanField(_("Is Pinned"), default=False)
    is_highlighted = models.BooleanField(_("Is Highlighted"), default=False)
    moderation_notes = models.TextField(_("Moderation Notes"), blank=True)
    flagged_count = models.PositiveIntegerField(
        _("Flagged Count"), default=0, editable=False
    )

    # Edit tracking
    is_edited = models.BooleanField(_("Is Edited"), default=False, editable=False)
    edit_count = models.PositiveIntegerField(_("Edit Count"), default=0, editable=False)
    edit_history = models.JSONField(
        _("Edit History"),
        default=list,
        blank=True,
        help_text=_("History of edits made to this comment"),
    )

    # Spam detection
    spam_score = models.FloatField(
        _("Spam Score"),
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )

    # Timestamps
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    approved_at = models.DateTimeField(_("Approved At"), null=True, blank=True)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_comments",
        verbose_name=_("Approved By"),
    )

    objects = BlogCommentQuerySet.as_manager()

    def __str__(self):
        return f"Comment by {self.author} on {self.post.title}"

    def save(self, *args, **kwargs):
        # Auto-approve comments from trusted users
        if (
            self.author
            and self.author.is_staff
            and self.status == self.CommentStatus.PENDING
        ):
            self.status = self.CommentStatus.APPROVED
            self.approved_at = timezone.now()
            self.approved_by = self.author

        super().save(*args, **kwargs)

    def get_depth(self):
        """Get the depth level of this comment in the thread."""
        depth = 0
        parent = self.parent
        while parent:
            depth += 1
            parent = parent.parent
        return depth

    def can_be_edited_by(self, user):
        """Check if user can edit this comment."""
        if not user or not user.is_authenticated:
            return False

        # Author can edit within time limit (e.g., 15 minutes)
        if user == self.author:
            time_limit = timedelta(minutes=15)
            return timezone.now() - self.created_at <= time_limit

        # Moderators can always edit
        return user.has_perm("blog.can_moderate_comments")

    def can_be_deleted_by(self, user):
        """Check if user can delete this comment."""
        if not user or not user.is_authenticated:
            return False

        # Author can delete their own comment
        if user == self.author:
            return True

        # Moderators can delete any comment
        return user.has_perm("blog.can_moderate_comments")

    def mark_as_spam(self, moderator=None):
        """Mark comment as spam."""
        self.status = self.CommentStatus.SPAM
        self.moderation_notes = f"Marked as spam by {moderator or 'system'}"
        self.save()

    def approve(self, moderator=None):
        """Approve the comment."""
        self.status = self.CommentStatus.APPROVED
        self.approved_at = timezone.now()
        self.approved_by = moderator
        self.save()


class BlogReaction(models.Model):
    """
    Reactions (likes, hearts, etc.) for posts and comments.
    """

    class ReactionType(models.TextChoices):
        LIKE = "like", _("👍 Like")
        HEART = "heart", _("❤️ Heart")
        LAUGH = "laugh", _("😂 Laugh")
        WOW = "wow", _("😮 Wow")
        SAD = "sad", _("😢 Sad")
        ANGRY = "angry", _("😠 Angry")
        BOOKMARK = "bookmark", _("🔖 Bookmark")

    class Meta:
        verbose_name = _("Blog Reaction")
        verbose_name_plural = _("Blog Reactions")
        unique_together = [["user", "content_type", "object_id", "reaction_type"]]
        indexes = [
            models.Index(fields=["content_type", "object_id", "reaction_type"]),
            models.Index(fields=["user", "created_at"]),
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="blog_reactions",
        verbose_name=_("User"),
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey("content_type", "object_id")
    reaction_type = models.CharField(
        _("Reaction Type"),
        max_length=20,
        choices=ReactionType.choices,
        default=ReactionType.LIKE,
    )
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    def __str__(self):
        return f"{self.user} {self.reaction_type} {self.content_object}"


class BlogView(models.Model):
    """
    Track post views for analytics with detailed metadata.
    """

    class Meta:
        verbose_name = _("Blog View")
        verbose_name_plural = _("Blog Views")
        indexes = [
            models.Index(fields=["post", "created_at"]),
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["created_at"]),
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(
        BlogPost, on_delete=models.CASCADE, related_name="views", verbose_name=_("Post")
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blog_views",
        verbose_name=_("User"),
    )
    session_key = models.CharField(_("Session Key"), max_length=40, blank=True)
    ip_address = models.GenericIPAddressField(_("IP Address"), null=True, blank=True)
    user_agent = models.TextField(_("User Agent"), blank=True)
    referrer = models.URLField(_("Referrer"), blank=True)
    device_type = models.CharField(
        _("Device Type"),
        max_length=20,
        choices=[
            ("desktop", _("Desktop")),
            ("mobile", _("Mobile")),
            ("tablet", _("Tablet")),
            ("bot", _("Bot")),
        ],
        blank=True,
    )
    country = models.CharField(_("Country"), max_length=2, blank=True)
    region = models.CharField(_("Region"), max_length=100, blank=True)
    city = models.CharField(_("City"), max_length=100, blank=True)
    duration = models.PositiveIntegerField(
        _("Duration"), default=0, help_text=_("Time spent reading in seconds")
    )
    scroll_depth = models.PositiveIntegerField(
        _("Scroll Depth"), default=0, help_text=_("Maximum scroll percentage")
    )
    is_bounce = models.BooleanField(_("Is Bounce"), default=True)
    utm_source = models.CharField(_("UTM Source"), max_length=100, blank=True)
    utm_medium = models.CharField(_("UTM Medium"), max_length=100, blank=True)
    utm_campaign = models.CharField(_("UTM Campaign"), max_length=100, blank=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    def __str__(self):
        return f"View of {self.post.title} by {self.user or 'Anonymous'}"


class BlogSubscription(models.Model):
    """
    Subscriptions for receiving notifications about new posts, comments, etc.
    """

    class SubscriptionType(models.TextChoices):
        AUTHOR = "author", _("Author")
        CATEGORY = "category", _("Category")
        TAG = "tag", _("Tag")
        POST = "post", _("Specific Post")
        ALL_POSTS = "all_posts", _("All Posts")

    class NotificationFrequency(models.TextChoices):
        INSTANT = "instant", _("Instant")
        DAILY = "daily", _("Daily Digest")
        WEEKLY = "weekly", _("Weekly Digest")
        MONTHLY = "monthly", _("Monthly Digest")

    class Meta:
        verbose_name = _("Blog Subscription")
        verbose_name_plural = _("Blog Subscriptions")
        unique_together = [["user", "subscription_type", "content_type", "object_id"]]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["subscription_type", "is_active"]),
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="blog_subscriptions",
        verbose_name=_("User"),
    )
    subscription_type = models.CharField(
        _("Subscription Type"), max_length=20, choices=SubscriptionType.choices
    )
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )
    object_id = models.UUIDField(null=True, blank=True)
    subscribed_to = GenericForeignKey("content_type", "object_id")

    # Notification preferences
    email_notifications = models.BooleanField(_("Email Notifications"), default=True)
    push_notifications = models.BooleanField(_("Push Notifications"), default=True)
    in_app_notifications = models.BooleanField(_("In-App Notifications"), default=True)
    notification_frequency = models.CharField(
        _("Notification Frequency"),
        max_length=20,
        choices=NotificationFrequency.choices,
        default=NotificationFrequency.INSTANT,
    )

    # Status
    is_active = models.BooleanField(_("Is Active"), default=True)
    unsubscribe_token = models.CharField(
        _("Unsubscribe Token"), max_length=64, unique=True
    )

    # Timestamps
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    last_notification_sent = models.DateTimeField(
        _("Last Notification Sent"), null=True, blank=True
    )

    def __str__(self):
        return f"{self.user} subscribed to {self.subscription_type}"

    def save(self, *args, **kwargs):
        if not self.unsubscribe_token:
            self.unsubscribe_token = hashlib.sha256(
                f"{self.user.id}{timezone.now().isoformat()}".encode()
            ).hexdigest()
        super().save(*args, **kwargs)


class BlogAnalytics(models.Model):
    """
    Comprehensive analytics for blog posts with AI-powered insights.
    """

    class Meta:
        verbose_name = _("Blog Analytics")
        verbose_name_plural = _("Blog Analytics")

    post = models.OneToOneField(
        BlogPost,
        on_delete=models.CASCADE,
        related_name="analytics",
        verbose_name=_("Post"),
    )

    # Basic metrics
    total_views = models.PositiveIntegerField(_("Total Views"), default=0)
    unique_views = models.PositiveIntegerField(_("Unique Views"), default=0)
    total_likes = models.PositiveIntegerField(_("Total Likes"), default=0)
    total_comments = models.PositiveIntegerField(_("Total Comments"), default=0)
    total_shares = models.PositiveIntegerField(_("Total Shares"), default=0)
    total_bookmarks = models.PositiveIntegerField(_("Total Bookmarks"), default=0)

    # Engagement metrics
    engagement_rate = models.FloatField(_("Engagement Rate"), default=0.0)
    bounce_rate = models.FloatField(_("Bounce Rate"), default=0.0)
    avg_reading_time = models.PositiveIntegerField(_("Avg Reading Time"), default=0)
    completion_rate = models.FloatField(_("Completion Rate"), default=0.0)

    # SEO metrics
    search_impressions = models.PositiveIntegerField(_("Search Impressions"), default=0)
    search_clicks = models.PositiveIntegerField(_("Search Clicks"), default=0)
    search_ctr = models.FloatField(_("Search CTR"), default=0.0)
    avg_search_position = models.FloatField(_("Avg Search Position"), default=0.0)

    # Traffic sources
    direct_traffic = models.PositiveIntegerField(_("Direct Traffic"), default=0)
    search_traffic = models.PositiveIntegerField(_("Search Traffic"), default=0)
    social_traffic = models.PositiveIntegerField(_("Social Traffic"), default=0)
    referral_traffic = models.PositiveIntegerField(_("Referral Traffic"), default=0)

    # Geographic data
    top_countries = models.JSONField(_("Top Countries"), default=dict, blank=True)
    top_cities = models.JSONField(_("Top Cities"), default=dict, blank=True)

    # Device data
    desktop_views = models.PositiveIntegerField(_("Desktop Views"), default=0)
    mobile_views = models.PositiveIntegerField(_("Mobile Views"), default=0)
    tablet_views = models.PositiveIntegerField(_("Tablet Views"), default=0)

    # Time-based data
    hourly_views = models.JSONField(_("Hourly Views"), default=dict, blank=True)
    daily_views = models.JSONField(_("Daily Views"), default=dict, blank=True)
    weekly_views = models.JSONField(_("Weekly Views"), default=dict, blank=True)

    # Conversion metrics
    newsletter_signups = models.PositiveIntegerField(_("Newsletter Signups"), default=0)
    downloads = models.PositiveIntegerField(_("Downloads"), default=0)
    contact_form_submissions = models.PositiveIntegerField(
        _("Contact Form Submissions"), default=0
    )

    # AI insights
    content_quality_score = models.FloatField(_("Content Quality Score"), default=0.0)
    readability_score = models.FloatField(_("Readability Score"), default=0.0)
    seo_score = models.FloatField(_("SEO Score"), default=0.0)
    sentiment_score = models.FloatField(_("Sentiment Score"), default=0.0)
    trending_score = models.FloatField(_("Trending Score"), default=0.0)
    virality_prediction = models.FloatField(_("Virality Prediction"), default=0.0)

    # Performance predictions
    predicted_views_7d = models.PositiveIntegerField(
        _("Predicted Views (7d)"), default=0
    )
    predicted_views_30d = models.PositiveIntegerField(
        _("Predicted Views (30d)"), default=0
    )

    # Timestamps
    last_updated = models.DateTimeField(_("Last Updated"), auto_now=True)
    last_calculated = models.DateTimeField(_("Last Calculated"), null=True, blank=True)

    def __str__(self):
        return f"Analytics for {self.post.title}"

    def calculate_engagement_rate(self):
        """Calculate engagement rate."""
        if self.total_views > 0:
            engagements = self.total_likes + self.total_comments + self.total_shares
            self.engagement_rate = (engagements / self.total_views) * 100
        else:
            self.engagement_rate = 0.0

    def calculate_bounce_rate(self):
        """Calculate bounce rate."""
        bounces = self.post.views.filter(is_bounce=True).count()
        if self.total_views > 0:
            self.bounce_rate = (bounces / self.total_views) * 100
        else:
            self.bounce_rate = 0.0

    def update_metrics(self):
        """Update all analytics metrics."""
        # Basic counts
        self.total_views = self.post.views.count()
        self.unique_views = (
            self.post.views.values("user", "session_key", "ip_address")
            .distinct()
            .count()
        )

        # Engagement metrics
        self.calculate_engagement_rate()
        self.calculate_bounce_rate()

        # Average reading time
        avg_time = (
            self.post.views.aggregate(avg_duration=models.Avg("duration"))[
                "avg_duration"
            ]
            or 0
        )
        self.avg_reading_time = int(avg_time)

        # Device breakdown
        device_stats = self.post.views.values("device_type").annotate(
            count=models.Count("id")
        )
        for stat in device_stats:
            device = stat["device_type"]
            count = stat["count"]
            if device == "desktop":
                self.desktop_views = count
            elif device == "mobile":
                self.mobile_views = count
            elif device == "tablet":
                self.tablet_views = count

        self.last_calculated = timezone.now()
        self.save()


# Signals for automatic updates and notifications
@receiver(pre_save, sender=BlogPost)
def update_search_vector(sender, instance, **kwargs):
    """Update search vector before saving post."""
    try:
        # Create search vector from title, content, and tags
        search_content = f"{instance.title} {instance.raw_content}"
        if instance.tags.exists():
            tags_text = " ".join(instance.tags.values_list("name", flat=True))
            search_content += f" {tags_text}"

        # instance.search_vector = (
        #     SearchVector("title", weight="A")
        #     + SearchVector("raw_content", weight="B")
        #     + SearchVector("excerpt", weight="C")
        # )  # Commented out for SQLite compatibility
    except Exception as e:
        logger.error(f"Error updating search vector: {e}")


@receiver(post_save, sender=BlogPost)
def post_blog_post_save(sender, instance, created, **kwargs):
    """Handle post-save operations for blog posts."""
    try:
        # Create analytics record if it doesn't exist
        if not hasattr(instance, "analytics"):
            BlogAnalytics.objects.create(post=instance)

        # Send notifications for published posts
        if instance.status == BlogPost.PostStatus.PUBLISHED and not created:
            instance.notify_subscribers("post_published")

        # Log activity
        from apps.audit_log.models import AuditLog

        AuditLog.objects.create(
            user=instance.author,
            action="blog_post_created" if created else "blog_post_updated",
            content_type=ContentType.objects.get_for_model(BlogPost),
            object_id=instance.pk,
            object_repr=str(instance),
            changes={"title": instance.title, "status": instance.status},
        )
    except Exception as e:
        logger.error(f"Error in post_blog_post_save: {e}")


@receiver(post_save, sender=BlogComment)
def post_blog_comment_save(sender, instance, created, **kwargs):
    """Handle post-save operations for blog comments."""
    try:
        if created:
            # Update comment count on post
            instance.post.comment_count = instance.post.comments.approved().count()
            instance.post.save(update_fields=["comment_count"])

            # Update reply count on parent comment
            if instance.parent:
                instance.parent.reply_count = instance.parent.replies.approved().count()
                instance.parent.save(update_fields=["reply_count"])

            # Send notification to post author and subscribers
            if instance.status == BlogComment.CommentStatus.APPROVED:
                instance.post.notify_subscribers("new_comment")

            # Log activity
            from apps.audit_log.models import AuditLog

            AuditLog.objects.create(
                user=instance.author,
                action="blog_comment_created",
                content_type=ContentType.objects.get_for_model(BlogComment),
                object_id=instance.pk,
                object_repr=str(instance),
            )
    except Exception as e:
        logger.error(f"Error in post_blog_comment_save: {e}")


@receiver(post_save, sender=BlogReaction)
def post_blog_reaction_save(sender, instance, created, **kwargs):
    """Handle post-save operations for blog reactions."""
    try:
        if created:
            # Update reaction counts
            if isinstance(instance.content_object, BlogPost):
                post = instance.content_object
                if instance.reaction_type == BlogReaction.ReactionType.LIKE:
                    post.like_count = post.reactions.filter(
                        reaction_type=BlogReaction.ReactionType.LIKE
                    ).count()
                    post.save(update_fields=["like_count"])

            elif isinstance(instance.content_object, BlogComment):
                comment = instance.content_object
                if instance.reaction_type == BlogReaction.ReactionType.LIKE:
                    comment.like_count = comment.reactions.filter(
                        reaction_type=BlogReaction.ReactionType.LIKE
                    ).count()
                    comment.save(update_fields=["like_count"])

            # Send real-time notification
            try:
                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(
                        f"blog_post_{instance.content_object.id}",
                        {
                            "type": "blog_notification",
                            "event": "new_reaction",
                            "reaction_type": instance.reaction_type,
                            "user": instance.user.get_full_name(),
                        },
                    )
            except Exception as e:
                logger.error(f"Failed to send reaction notification: {e}")

    except Exception as e:
        logger.error(f"Error in post_blog_reaction_save: {e}")


@receiver(m2m_changed, sender=BlogPost.tags.through)
def update_tag_usage_count(sender, instance, action, pk_set, **kwargs):
    """Update tag usage counts when tags are added/removed from posts."""
    try:
        if action in ["post_add", "post_remove"]:
            for tag_pk in pk_set or []:
                try:
                    tag = BlogTag.objects.get(pk=tag_pk)
                    tag.usage_count = tag.blog_posts.published().count()
                    tag.save(update_fields=["usage_count"])
                except BlogTag.DoesNotExist:
                    continue
    except Exception as e:
        logger.error(f"Error updating tag usage count: {e}")


@receiver(m2m_changed, sender=BlogPost.categories.through)
def update_category_post_count(sender, instance, action, pk_set, **kwargs):
    """Update category post counts when posts are added/removed from categories."""
    try:
        if action in ["post_add", "post_remove"]:
            for category_pk in pk_set or []:
                try:
                    category = BlogCategory.objects.get(pk=category_pk)
                    category.post_count = category.blog_posts.published().count()
                    category.save(update_fields=["post_count"])
                except BlogCategory.DoesNotExist:
                    continue
    except Exception as e:
        logger.error(f"Error updating category post count: {e}")


# Additional models for advanced features


class BlogSeries(models.Model):
    """
    Blog series for grouping related posts.
    """

    class Meta:
        verbose_name = _("Blog Series")
        verbose_name_plural = _("Blog Series")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["author", "-created_at"]),
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(_("Title"), max_length=200)
    slug = models.SlugField(_("Slug"), unique=True, max_length=220)
    description = models.TextField(_("Description"), blank=True, max_length=1000)
    cover_image = models.ImageField(
        _("Cover Image"), upload_to="blog/series_covers/", blank=True, null=True
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="blog_series",
        verbose_name=_("Author"),
    )
    posts = models.ManyToManyField(
        BlogPost,
        through="BlogSeriesPost",
        related_name="series",
        verbose_name=_("Posts"),
    )
    is_active = models.BooleanField(_("Is Active"), default=True)
    is_completed = models.BooleanField(_("Is Completed"), default=False)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("blog:series_detail", kwargs={"slug": self.slug})


class BlogSeriesPost(models.Model):
    """
    Through model for BlogSeries and BlogPost relationship.
    """

    class Meta:
        verbose_name = _("Blog Series Post")
        verbose_name_plural = _("Blog Series Posts")
        ordering = ["order"]
        unique_together = [["series", "post"], ["series", "order"]]

    series = models.ForeignKey(BlogSeries, on_delete=models.CASCADE)
    post = models.ForeignKey(BlogPost, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(_("Order"))
    added_at = models.DateTimeField(_("Added At"), auto_now_add=True)

    def __str__(self):
        return f"{self.series.title} - {self.post.title} (#{self.order})"


class BlogNewsletter(models.Model):
    """
    Newsletter for blog subscribers.
    """

    class NewsletterStatus(models.TextChoices):
        DRAFT = "draft", _("Draft")
        SCHEDULED = "scheduled", _("Scheduled")
        SENT = "sent", _("Sent")
        CANCELLED = "cancelled", _("Cancelled")

    class Meta:
        verbose_name = _("Blog Newsletter")
        verbose_name_plural = _("Blog Newsletters")
        ordering = ["-created_at"]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject = models.CharField(_("Subject"), max_length=200)
    content = models.JSONField(_("Content"), default=dict)
    featured_posts = models.ManyToManyField(
        BlogPost,
        blank=True,
        related_name="newsletters",
        verbose_name=_("Featured Posts"),
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=NewsletterStatus.choices,
        default=NewsletterStatus.DRAFT,
    )
    scheduled_date = models.DateTimeField(_("Scheduled Date"), null=True, blank=True)
    sent_date = models.DateTimeField(_("Sent Date"), null=True, blank=True)
    recipient_count = models.PositiveIntegerField(
        _("Recipient Count"), default=0, editable=False
    )
    open_rate = models.FloatField(_("Open Rate"), default=0.0, editable=False)
    click_rate = models.FloatField(_("Click Rate"), default=0.0, editable=False)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_newsletters",
        verbose_name=_("Created By"),
    )

    def __str__(self):
        return self.subject


class BlogBadge(models.Model):
    """
    Gamification badges for blog users.
    """

    class BadgeType(models.TextChoices):
        AUTHOR = "author", _("Author Badge")
        READER = "reader", _("Reader Badge")
        COMMENTER = "commenter", _("Commenter Badge")
        SHARER = "sharer", _("Sharer Badge")
        MILESTONE = "milestone", _("Milestone Badge")

    class Meta:
        verbose_name = _("Blog Badge")
        verbose_name_plural = _("Blog Badges")
        ordering = ["badge_type", "level"]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Name"), max_length=100)
    description = models.TextField(_("Description"), blank=True)
    badge_type = models.CharField(
        _("Badge Type"), max_length=20, choices=BadgeType.choices
    )
    level = models.PositiveIntegerField(_("Level"), default=1)
    icon = models.ImageField(_("Icon"), upload_to="blog/badges/", blank=True, null=True)
    color = models.CharField(_("Color"), max_length=7, default="#6366f1")
    criteria = models.JSONField(
        _("Criteria"), default=dict, help_text=_("Criteria for earning this badge")
    )
    points = models.PositiveIntegerField(_("Points"), default=0)
    is_active = models.BooleanField(_("Is Active"), default=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    def __str__(self):
        return f"{self.name} (Level {self.level})"


class UserBlogBadge(models.Model):
    """
    User-earned blog badges.
    """

    class Meta:
        verbose_name = _("User Blog Badge")
        verbose_name_plural = _("User Blog Badges")
        unique_together = [["user", "badge"]]
        ordering = ["-earned_at"]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="blog_badges",
        verbose_name=_("User"),
    )
    badge = models.ForeignKey(
        BlogBadge,
        on_delete=models.CASCADE,
        related_name="user_badges",
        verbose_name=_("Badge"),
    )
    earned_at = models.DateTimeField(_("Earned At"), auto_now_add=True)
    progress = models.JSONField(
        _("Progress"),
        default=dict,
        blank=True,
        help_text=_("Progress towards earning the badge"),
    )

    def __str__(self):
        return f"{self.user} - {self.badge.name}"


class BlogModerationLog(models.Model):
    """
    Log for moderation actions on blog content.
    """

    class ActionType(models.TextChoices):
        APPROVE = "approve", _("Approve")
        REJECT = "reject", _("Reject")
        DELETE = "delete", _("Delete")
        EDIT = "edit", _("Edit")
        FEATURE = "feature", _("Feature")
        UNFEATURE = "unfeature", _("Unfeature")
        BAN_USER = "ban_user", _("Ban User")
        WARN_USER = "warn_user", _("Warn User")

    class Meta:
        verbose_name = _("Blog Moderation Log")
        verbose_name_plural = _("Blog Moderation Logs")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["moderator", "-created_at"]),
            models.Index(fields=["action_type", "-created_at"]),
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    moderator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="blog_moderation_actions",
        verbose_name=_("Moderator"),
    )
    action_type = models.CharField(
        _("Action Type"), max_length=20, choices=ActionType.choices
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey("content_type", "object_id")
    reason = models.TextField(_("Reason"), blank=True)
    notes = models.TextField(_("Notes"), blank=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    def __str__(self):
        return f"{self.action_type} by {self.moderator} on {self.content_object}"


class BlogReadingList(models.Model):
    """
    User reading lists for organizing saved posts.
    """

    class Privacy(models.TextChoices):
        PUBLIC = "public", _("Public")
        PRIVATE = "private", _("Private")
        FOLLOWERS = "followers", _("Followers Only")

    class Meta:
        verbose_name = _("Blog Reading List")
        verbose_name_plural = _("Blog Reading Lists")
        ordering = ["-created_at"]
        unique_together = [["user", "name"]]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="reading_lists",
        verbose_name=_("User"),
    )
    name = models.CharField(_("Name"), max_length=100)
    description = models.TextField(_("Description"), blank=True, max_length=500)
    posts = models.ManyToManyField(
        BlogPost, blank=True, related_name="reading_lists", verbose_name=_("Posts")
    )
    privacy = models.CharField(
        _("Privacy"), max_length=20, choices=Privacy.choices, default=Privacy.PRIVATE
    )
    is_default = models.BooleanField(_("Is Default"), default=False)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s {self.name}"

    def save(self, *args, **kwargs):
        # Ensure only one default list per user
        if self.is_default:
            self.__class__.objects.filter(user=self.user, is_default=True).exclude(
                pk=self.pk
            ).update(is_default=False)
        super().save(*args, **kwargs)
