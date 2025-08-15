import logging
from datetime import timedelta
from typing import Any, Dict

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.db.models import Avg, Count, F, Prefetch, Q
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.accounts.views.user import StandardResultsSetPagination
from apps.notifications.tasks import send_notification

from .exceptions import (
    CommentCreationLimitExceeded,
    CommentOnClosedPost,
    PostCreationLimitExceeded,
    PostNotFound,
    SelfReactionError,
    UnauthorizedPostAccess,
    UnauthorizedPostDelete,
    UnauthorizedPostEdit,
)
from .filters import (
    BlogCategoryFilter,
    BlogCommentFilter,
    BlogPostFilter,
    BlogTagFilter,
)
from .models import (
    BlogAnalytics,
    BlogCategory,
    BlogComment,
    BlogModerationLog,
    BlogPost,
    BlogReaction,
    BlogTag,
    BlogView,
    UserBlogBadge,
)
from .permissions import (
    BlogPermissionMixin,
    CanCommentOnPost,
    CanDeleteBlogPost,
    CanDeleteComment,
    CanEditBlogPost,
    CanEditComment,
    CanManageCategories,
    CanManageTags,
    CanModerateBlogPost,
    CanViewAnalytics,
    IsBlogModerator,
    RateLimitedBlogPermission,
    can_moderate_content,
    can_view_blog_post,
)
from .serializers import (
    AuthorStatsSerializer,
    BlogAnalyticsSerializer,
    BlogCategorySerializer,
    BlogCategoryStatsSerializer,
    BlogCategoryTreeSerializer,
    BlogCommentModerateSerializer,
    BlogCommentSerializer,
    BlogDashboardStatsSerializer,
    BlogPostCreateUpdateSerializer,
    BlogPostDetailSerializer,
    BlogPostListSerializer,
    BlogPostModerateSerializer,
    BlogPostSearchSerializer,
    BlogPostSitemapSerializer,
    BlogReactionSerializer,
    BlogTagSerializer,
    BlogTagStatsSerializer,
    BulkCommentActionSerializer,
    BulkPostActionSerializer,
)
from .tasks import (
    send_comment_notification,
    update_post_analytics,
    update_user_badge_progress,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class BlogThrottle(UserRateThrottle):
    """Custom throttle for blog operations."""

    scope = "blog"


class BlogPostViewSet(viewsets.ModelViewSet, BlogPermissionMixin):
    """
    ViewSet for managing blog posts.

    Provides CRUD operations, filtering, search, and advanced features like:
    - Draft/publish workflow
    - Reactions (like, dislike, etc.)
    - Analytics tracking
    - Related posts
    - Trending posts
    - Featured posts
    """

    pagination_class = StandardResultsSetPagination
    throttle_classes = [BlogThrottle, AnonRateThrottle]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = BlogPostFilter
    search_fields = [
        "title",
        "content",
        "excerpt",
        "author__first_name",
        "author__last_name",
    ]
    ordering_fields = [
        "created_at",
        "updated_at",
        "published_at",
        "title",
        "reading_time",
    ]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Get posts based on user permissions and filters."""
        queryset = BlogPost.objects.select_related(
            "author", "author__userprofile"
        ).prefetch_related(
            "categories",
            "tags",
            "attachments",
            Prefetch(
                "comments",
                queryset=BlogComment.objects.filter(
                    status=BlogComment.CommentStatus.APPROVED
                ),
            ),
            "reactions",
        )

        # Filter based on action and permissions
        if self.action == "list":
            # Public listing - only show published and public posts
            if not self.request.user.is_authenticated:
                queryset = queryset.filter(
                    status=BlogPost.PostStatus.PUBLISHED,
                    visibility=BlogPost.Visibility.PUBLIC,
                )
            else:
                # Authenticated users can see their own posts + public published posts
                queryset = queryset.filter(
                    Q(status=BlogPost.PostStatus.PUBLISHED)
                    | Q(author=self.request.user)
                ).filter(
                    Q(visibility=BlogPost.Visibility.PUBLIC)
                    | Q(visibility=BlogPost.Visibility.AUTHENTICATED)
                    | Q(author=self.request.user)
                )
        elif self.action in ["my_posts", "my_drafts"]:
            # User's own posts
            if self.request.user.is_authenticated:
                queryset = queryset.filter(author=self.request.user)
            else:
                queryset = queryset.none()
        elif self.action == "moderation_queue":
            # Moderation queue - only for moderators
            if can_moderate_content(self.request.user):
                queryset = queryset.filter(status=BlogPost.PostStatus.UNDER_REVIEW)
            else:
                queryset = queryset.none()

        return queryset

    def get_serializer_class(self):
        """Get appropriate serializer based on action."""
        if self.action == "list":
            return BlogPostListSerializer
        elif self.action in ["create", "update", "partial_update"]:
            return BlogPostCreateUpdateSerializer
        elif self.action == "moderate":
            return BlogPostModerateSerializer
        elif self.action == "search":
            return BlogPostSearchSerializer
        elif self.action == "sitemap":
            return BlogPostSitemapSerializer
        else:
            return BlogPostDetailSerializer

    def get_permissions(self):
        """Get permissions based on action."""
        if self.action in [
            "list",
            "retrieve",
            "search",
            "trending",
            "featured",
            "popular",
            "sitemap",
        ]:
            permission_classes = [permissions.AllowAny]
        elif self.action in ["create"]:
            permission_classes = [
                permissions.IsAuthenticated,
                RateLimitedBlogPermission,
            ]
        elif self.action in ["update", "partial_update"]:
            permission_classes = [permissions.IsAuthenticated, CanEditBlogPost]
        elif self.action in ["destroy"]:
            permission_classes = [permissions.IsAuthenticated, CanDeleteBlogPost]
        elif self.action in ["moderate", "bulk_moderate", "moderation_queue"]:
            permission_classes = [permissions.IsAuthenticated, CanModerateBlogPost]
        elif self.action in ["my_posts", "my_drafts", "analytics"]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated]

        return [permission() for permission in permission_classes]

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    def list(self, request, *args, **kwargs):
        """List blog posts with caching."""
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error listing blog posts: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to retrieve blog posts"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def retrieve(self, request, *args, **kwargs):
        """Retrieve a single blog post and track view."""
        try:
            instance = self.get_object()

            # Check viewing permissions
            if not can_view_blog_post(request.user, instance):
                raise UnauthorizedPostAccess()

            # Track view asynchronously
            if request.user.is_authenticated:
                update_post_analytics.delay(instance.id, request.user.id, "view")
            else:
                # Track anonymous view
                update_post_analytics.delay(
                    instance.id,
                    None,
                    "view",
                    ip_address=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT"),
                )

            serializer = self.get_serializer(instance)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error retrieving blog post: {str(e)}", exc_info=True)
            if isinstance(e, (UnauthorizedPostAccess, PostNotFound)):
                raise
            return Response(
                {"error": "Failed to retrieve blog post"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Create a new blog post."""
        try:
            # Check rate limits
            self.check_blog_permissions(request, action="create")

            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            post = serializer.save()

            # Send notifications if published
            if post.status == BlogPost.PostStatus.PUBLISHED:
                send_notification.delay("new_post", post.id, post.author.id)

            # Update user badges
            update_user_badge_progress.delay(post.author.id, "post_created")

            headers = self.get_success_headers(serializer.data)
            return Response(
                serializer.data, status=status.HTTP_201_CREATED, headers=headers
            )
        except Exception as e:
            logger.error(f"Error creating blog post: {str(e)}", exc_info=True)
            if isinstance(e, (ValidationError, PostCreationLimitExceeded)):
                raise
            return Response(
                {"error": "Failed to create blog post"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        """Update a blog post."""
        try:
            instance = self.get_object()
            self.check_blog_permissions(request, instance, action="edit")

            serializer = self.get_serializer(
                instance, data=request.data, partial=kwargs.get("partial", False)
            )
            serializer.is_valid(raise_exception=True)

            # Check if status changed to published
            old_status = instance.status
            post = serializer.save()

            if (
                old_status != BlogPost.PostStatus.PUBLISHED
                and post.status == BlogPost.PostStatus.PUBLISHED
            ):
                send_notification.delay("post_published", post.id, post.author.id)

            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error updating blog post: {str(e)}", exc_info=True)
            if isinstance(e, (ValidationError, UnauthorizedPostEdit)):
                raise
            return Response(
                {"error": "Failed to update blog post"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        """Delete a blog post."""
        try:
            instance = self.get_object()
            self.check_blog_permissions(request, instance, action="delete")

            # Log deletion
            BlogModerationLog.objects.create(
                moderator=request.user,
                action_type=BlogModerationLog.ActionType.DELETE,
                content_object=instance,
                description=f"Post '{instance.title}' deleted",
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )

            instance.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            logger.error(f"Error deleting blog post: {str(e)}", exc_info=True)
            if isinstance(e, UnauthorizedPostDelete):
                raise
            return Response(
                {"error": "Failed to delete blog post"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Blog Posts"], responses={200: BlogPostListSerializer(many=True)}
    )
    @action(detail=False, methods=["get"])
    def trending(self, request):
        """Get trending blog posts."""
        try:
            cache_key = "blog_trending_posts"
            cached_posts = cache.get(cache_key)

            if cached_posts is None:
                # Calculate trending posts based on recent views, reactions, and comments
                trending_posts = (
                    BlogPost.objects.filter(
                        status=BlogPost.PostStatus.PUBLISHED,
                        visibility=BlogPost.Visibility.PUBLIC,
                        published_at__gte=timezone.now() - timedelta(days=7),
                    )
                    .annotate(
                        trending_score=F("views_count")
                        + F("reactions_count") * 2
                        + F("comments_count") * 3
                    )
                    .order_by("-trending_score")[:20]
                )

                serializer = BlogPostListSerializer(
                    trending_posts, many=True, context={"request": request}
                )
                cached_posts = serializer.data
                cache.set(cache_key, cached_posts, 60 * 30)  # Cache for 30 minutes

            return Response(cached_posts)
        except Exception as e:
            logger.error(f"Error getting trending posts: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get trending posts"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Blog Posts"], responses={200: BlogPostListSerializer(many=True)}
    )
    @action(detail=False, methods=["get"])
    def featured(self, request):
        """Get featured blog posts."""
        try:
            cache_key = "blog_featured_posts"
            cached_posts = cache.get(cache_key)

            if cached_posts is None:
                featured_posts = BlogPost.objects.filter(
                    status=BlogPost.PostStatus.PUBLISHED,
                    visibility=BlogPost.Visibility.PUBLIC,
                    is_featured=True,
                ).order_by("-published_at")[:10]

                serializer = BlogPostListSerializer(
                    featured_posts, many=True, context={"request": request}
                )
                cached_posts = serializer.data
                cache.set(cache_key, cached_posts, 60 * 60)  # Cache for 1 hour

            return Response(cached_posts)
        except Exception as e:
            logger.error(f"Error getting featured posts: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get featured posts"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Blog Posts"], responses={200: BlogPostListSerializer(many=True)}
    )
    @action(detail=False, methods=["get"])
    def popular(self, request):
        """Get popular blog posts."""
        try:
            cache_key = "blog_popular_posts"
            cached_posts = cache.get(cache_key)

            if cached_posts is None:
                popular_posts = BlogPost.objects.filter(
                    status=BlogPost.PostStatus.PUBLISHED,
                    visibility=BlogPost.Visibility.PUBLIC,
                ).order_by("-views_count", "-reactions_count")[:20]

                serializer = BlogPostListSerializer(
                    popular_posts, many=True, context={"request": request}
                )
                cached_posts = serializer.data
                cache.set(cache_key, cached_posts, 60 * 60)  # Cache for 1 hour

            return Response(cached_posts)
        except Exception as e:
            logger.error(f"Error getting popular posts: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get popular posts"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Blog Posts"], responses={200: BlogPostListSerializer(many=True)}
    )
    @action(
        detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated]
    )
    def my_posts(self, request):
        """Get current user's blog posts."""
        try:
            queryset = self.filter_queryset(self.get_queryset())
            page = self.paginate_queryset(queryset)

            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting user posts: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get your posts"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Blog Posts"], responses={200: BlogPostListSerializer(many=True)}
    )
    @action(
        detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated]
    )
    def my_drafts(self, request):
        """Get current user's draft posts."""
        try:
            drafts = self.get_queryset().filter(status=BlogPost.PostStatus.DRAFT)
            page = self.paginate_queryset(drafts)

            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(drafts, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting user drafts: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get your drafts"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Blog Posts"],
        parameters=[
            OpenApiParameter(
                name="q", description="Search query", required=True, type=str
            ),
        ],
        responses={200: BlogPostSearchSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def search(self, request):
        """Advanced search for blog posts."""
        try:
            query = request.query_params.get("q", "").strip()
            if not query:
                return Response(
                    {"error": "Search query is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Cache search results
            cache_key = f"blog_search_{hash(query)}"
            cached_results = cache.get(cache_key)

            if cached_results is None:
                # Perform search across multiple fields
                posts = (
                    BlogPost.objects.filter(
                        Q(title__icontains=query)
                        | Q(content__icontains=query)
                        | Q(excerpt__icontains=query)
                        | Q(tags__name__icontains=query)
                        | Q(categories__name__icontains=query),
                        status=BlogPost.PostStatus.PUBLISHED,
                        visibility=BlogPost.Visibility.PUBLIC,
                    )
                    .distinct()
                    .order_by("-published_at")[:50]
                )

                serializer = BlogPostSearchSerializer(
                    posts, many=True, context={"request": request}
                )
                cached_results = serializer.data
                cache.set(cache_key, cached_results, 60 * 15)  # Cache for 15 minutes

            return Response(cached_results)
        except Exception as e:
            logger.error(f"Error searching posts: {str(e)}", exc_info=True)
            return Response(
                {"error": "Search failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @extend_schema(
        tags=["Blog Posts"],
        request=BlogReactionSerializer,
        responses={201: BlogReactionSerializer},
    )
    @action(
        detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated]
    )
    def react(self, request, pk=None):
        """Add or update reaction to a blog post."""
        try:
            post = self.get_object()

            if not can_view_blog_post(request.user, post):
                raise UnauthorizedPostAccess()

            if post.author == request.user:
                raise SelfReactionError()

            serializer = BlogReactionSerializer(
                data=request.data, context={"request": request, "post": post}
            )
            serializer.is_valid(raise_exception=True)

            serializer.save()

            # Update analytics
            update_post_analytics.delay(post.id, request.user.id, "reaction")

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"Error adding reaction: {str(e)}", exc_info=True)
            if isinstance(e, (UnauthorizedPostAccess, SelfReactionError)):
                raise
            return Response(
                {"error": "Failed to add reaction"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(tags=["Blog Posts"], responses={204: None})
    @action(
        detail=True,
        methods=["delete"],
        permission_classes=[permissions.IsAuthenticated],
    )
    def unreact(self, request, pk=None):
        """Remove reaction from a blog post."""
        try:
            post = self.get_object()

            reaction = BlogReaction.objects.filter(user=request.user, post=post).first()
            if not reaction:
                return Response(
                    {"error": "No reaction found"}, status=status.HTTP_404_NOT_FOUND
                )

            reaction.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            logger.error(f"Error removing reaction: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to remove reaction"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(tags=["Blog Posts"], responses={200: BlogAnalyticsSerializer})
    @action(
        detail=True,
        methods=["get"],
        permission_classes=[permissions.IsAuthenticated, CanViewAnalytics],
    )
    def analytics(self, request, pk=None):
        """Get analytics for a blog post."""
        try:
            post = self.get_object()

            try:
                analytics = post.analytics
                serializer = BlogAnalyticsSerializer(analytics)
                return Response(serializer.data)
            except BlogAnalytics.DoesNotExist:
                return Response(
                    {"error": "Analytics not available"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        except Exception as e:
            logger.error(f"Error getting post analytics: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get analytics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Blog Posts"],
        request=BlogPostModerateSerializer,
        responses={200: BlogPostDetailSerializer},
    )
    @action(
        detail=True,
        methods=["patch"],
        permission_classes=[permissions.IsAuthenticated, CanModerateBlogPost],
    )
    def moderate(self, request, pk=None):
        """Moderate a blog post (approve/reject/feature)."""
        try:
            post = self.get_object()

            serializer = BlogPostModerateSerializer(
                post, data=request.data, partial=True, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()

            # Return updated post
            response_serializer = BlogPostDetailSerializer(
                post, context={"request": request}
            )
            return Response(response_serializer.data)
        except Exception as e:
            logger.error(f"Error moderating post: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to moderate post"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Blog Posts"], responses={200: BlogPostListSerializer(many=True)}
    )
    @action(
        detail=False,
        methods=["get"],
        permission_classes=[permissions.IsAuthenticated, CanModerateBlogPost],
    )
    def moderation_queue(self, request):
        """Get posts pending moderation."""
        try:
            queryset = self.filter_queryset(self.get_queryset())
            page = self.paginate_queryset(queryset)

            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting moderation queue: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get moderation queue"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Blog Posts"],
        request=BulkPostActionSerializer,
        responses={
            200: {"type": "object", "properties": {"message": {"type": "string"}}}
        },
    )
    @action(
        detail=False,
        methods=["post"],
        permission_classes=[permissions.IsAuthenticated, CanModerateBlogPost],
    )
    def bulk_moderate(self, request):
        """Perform bulk moderation actions on posts."""
        try:
            serializer = BulkPostActionSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            post_ids = serializer.validated_data["post_ids"]
            action = serializer.validated_data["action"]
            reason = serializer.validated_data.get("reason", "")

            posts = BlogPost.objects.filter(id__in=post_ids)
            updated_count = 0

            with transaction.atomic():
                for post in posts:
                    if action == "publish":
                        post.status = BlogPost.PostStatus.PUBLISHED
                        post.published_at = timezone.now()
                    elif action == "unpublish":
                        post.status = BlogPost.PostStatus.DRAFT
                        post.published_at = None
                    elif action == "feature":
                        post.is_featured = True
                    elif action == "unfeature":
                        post.is_featured = False
                    elif action == "delete":
                        post.delete()
                        continue

                    post.save()
                    updated_count += 1

                    # Log moderation action
                    BlogModerationLog.objects.create(
                        moderator=request.user,
                        action_type=getattr(
                            BlogModerationLog.ActionType, action.upper(), "OTHER"
                        ),
                        content_object=post,
                        description=reason or f"Bulk {action}",
                        ip_address=request.META.get("REMOTE_ADDR"),
                        user_agent=request.META.get("HTTP_USER_AGENT", ""),
                    )

            return Response(
                {"message": f"Successfully {action}ed {updated_count} posts"}
            )
        except Exception as e:
            logger.error(f"Error in bulk moderation: {str(e)}", exc_info=True)
            return Response(
                {"error": "Bulk moderation failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Blog Posts"], responses={200: BlogPostSitemapSerializer(many=True)}
    )
    @method_decorator(cache_page(60 * 60 * 24))  # Cache for 24 hours
    @action(detail=False, methods=["get"])
    def sitemap(self, request):
        """Get posts for sitemap generation."""
        try:
            posts = (
                BlogPost.objects.filter(
                    status=BlogPost.PostStatus.PUBLISHED,
                    visibility=BlogPost.Visibility.PUBLIC,
                )
                .values("slug", "updated_at", "published_at")
                .order_by("-published_at")
            )

            serializer = BlogPostSitemapSerializer(posts, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error generating sitemap: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to generate sitemap"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class BlogCategoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing blog categories.

    Provides hierarchical category management with:
    - Tree structure support
    - Category statistics
    - Post filtering
    """

    serializer_class = BlogCategorySerializer
    pagination_class = StandardResultsSetPagination
    throttle_classes = [BlogThrottle]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = BlogCategoryFilter
    search_fields = ["name", "description"]
    ordering_fields = ["name", "sort_order", "created_at"]
    ordering = ["sort_order", "name"]

    def get_queryset(self):
        """Get categories with proper filtering."""
        queryset = BlogCategory.objects.filter(is_active=True).select_related("parent")

        # For tree view, get root categories only
        if self.action == "tree":
            queryset = queryset.filter(parent__isnull=True)

        return queryset

    def get_serializer_class(self):
        """Get appropriate serializer based on action."""
        if self.action == "tree":
            return BlogCategoryTreeSerializer
        elif self.action == "stats":
            return BlogCategoryStatsSerializer
        else:
            return BlogCategorySerializer

    def get_permissions(self):
        """Get permissions based on action."""
        if self.action in ["list", "retrieve", "tree", "stats"]:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [permissions.IsAuthenticated, CanManageCategories]

        return [permission() for permission in permission_classes]

    @extend_schema(
        tags=["Blog Categories"], responses={200: BlogCategoryTreeSerializer(many=True)}
    )
    @method_decorator(cache_page(60 * 30))  # Cache for 30 minutes
    @action(detail=False, methods=["get"])
    def tree(self, request):
        """Get category tree structure."""
        try:
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting category tree: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get category tree"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Blog Categories"],
        responses={200: BlogCategoryStatsSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Get category statistics."""
        try:
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting category stats: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get category statistics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Blog Categories"],
        parameters=[
            OpenApiParameter(
                name="category_id", description="Category ID", required=True, type=int
            ),
        ],
        responses={200: BlogPostListSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def posts(self, request, pk=None):
        """Get posts in a specific category."""
        try:
            category = self.get_object()
            posts = BlogPost.objects.filter(
                categories=category,
                status=BlogPost.PostStatus.PUBLISHED,
                visibility=BlogPost.Visibility.PUBLIC,
            ).order_by("-published_at")

            page = self.paginate_queryset(posts)
            if page is not None:
                serializer = BlogPostListSerializer(
                    page, many=True, context={"request": request}
                )
                return self.get_paginated_response(serializer.data)

            serializer = BlogPostListSerializer(
                posts, many=True, context={"request": request}
            )
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting category posts: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get category posts"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class BlogTagViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing blog tags.

    Provides tag management with:
    - Popular and trending tags
    - Tag usage statistics
    - Post filtering by tags
    """

    serializer_class = BlogTagSerializer
    pagination_class = StandardResultsSetPagination
    throttle_classes = [BlogThrottle]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = BlogTagFilter
    search_fields = ["name", "description"]
    ordering_fields = ["name", "usage_count", "created_at"]
    ordering = ["-usage_count", "name"]

    def get_queryset(self):
        """Get tags with proper filtering."""
        return BlogTag.objects.all()

    def get_serializer_class(self):
        """Get appropriate serializer based on action."""
        if self.action == "stats":
            return BlogTagStatsSerializer
        else:
            return BlogTagSerializer

    def get_permissions(self):
        """Get permissions based on action."""
        if self.action in ["list", "retrieve", "popular", "trending", "stats"]:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [permissions.IsAuthenticated, CanManageTags]

        return [permission() for permission in permission_classes]

    @extend_schema(tags=["Blog Tags"], responses={200: BlogTagSerializer(many=True)})
    @method_decorator(cache_page(60 * 15))  # Cache for 15 minutes
    @action(detail=False, methods=["get"])
    def popular(self, request):
        """Get popular tags."""
        try:
            popular_tags = BlogTag.objects.filter(usage_count__gt=0).order_by(
                "-usage_count"
            )[:20]

            serializer = self.get_serializer(popular_tags, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting popular tags: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get popular tags"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(tags=["Blog Tags"], responses={200: BlogTagSerializer(many=True)})
    @action(detail=False, methods=["get"])
    def trending(self, request):
        """Get trending tags."""
        try:
            # Get tags with recent activity
            trending_tags = (
                BlogTag.objects.filter(
                    blogpost__status=BlogPost.PostStatus.PUBLISHED,
                    blogpost__created_at__gte=timezone.now() - timedelta(days=7),
                )
                .annotate(recent_usage=Count("blogpost"))
                .filter(recent_usage__gt=0)
                .order_by("-recent_usage")[:15]
            )

            serializer = self.get_serializer(trending_tags, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting trending tags: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get trending tags"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Blog Tags"],
        parameters=[
            OpenApiParameter(
                name="tag_id", description="Tag ID", required=True, type=int
            ),
        ],
        responses={200: BlogPostListSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def posts(self, request, pk=None):
        """Get posts with a specific tag."""
        try:
            tag = self.get_object()
            posts = BlogPost.objects.filter(
                tags=tag,
                status=BlogPost.PostStatus.PUBLISHED,
                visibility=BlogPost.Visibility.PUBLIC,
            ).order_by("-published_at")

            page = self.paginate_queryset(posts)
            if page is not None:
                serializer = BlogPostListSerializer(
                    page, many=True, context={"request": request}
                )
                return self.get_paginated_response(serializer.data)

            serializer = BlogPostListSerializer(
                posts, many=True, context={"request": request}
            )
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting tag posts: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get tag posts"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class BlogCommentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing blog comments.

    Provides comment management with:
    - Threaded comments
    - Comment moderation
    - Spam detection
    """

    serializer_class = BlogCommentSerializer
    pagination_class = StandardResultsSetPagination
    throttle_classes = [BlogThrottle]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = BlogCommentFilter
    search_fields = ["content", "author__first_name", "author__last_name"]
    ordering_fields = ["created_at", "updated_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Get comments with proper filtering."""
        queryset = BlogComment.objects.select_related(
            "author", "author__userprofile", "post", "parent"
        ).prefetch_related("replies")

        # Filter by post if specified
        post_id = self.kwargs.get("post_pk") or self.request.query_params.get("post_id")
        if post_id:
            queryset = queryset.filter(post_id=post_id)

        # Filter based on action and permissions
        if self.action == "list":
            # Only show approved comments for public listing
            if not self.request.user.is_authenticated or not can_moderate_content(
                self.request.user
            ):
                queryset = queryset.filter(status=BlogComment.CommentStatus.APPROVED)
        elif self.action == "moderation_queue":
            # Only for moderators
            if can_moderate_content(self.request.user):
                queryset = queryset.filter(status=BlogComment.CommentStatus.PENDING)
            else:
                queryset = queryset.none()

        return queryset

    def get_serializer_class(self):
        """Get appropriate serializer based on action."""
        if self.action == "moderate":
            return BlogCommentModerateSerializer
        else:
            return BlogCommentSerializer

    def get_permissions(self):
        """Get permissions based on action."""
        if self.action in ["list", "retrieve"]:
            permission_classes = [permissions.AllowAny]
        elif self.action in ["create"]:
            permission_classes = [permissions.IsAuthenticated, CanCommentOnPost]
        elif self.action in ["update", "partial_update"]:
            permission_classes = [permissions.IsAuthenticated, CanEditComment]
        elif self.action in ["destroy"]:
            permission_classes = [permissions.IsAuthenticated, CanDeleteComment]
        elif self.action in ["moderate", "bulk_moderate", "moderation_queue"]:
            permission_classes = [permissions.IsAuthenticated, IsBlogModerator]
        else:
            permission_classes = [permissions.IsAuthenticated]

        return [permission() for permission in permission_classes]

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Create a new comment."""
        try:
            # Get post from URL or data
            post_id = self.kwargs.get("post_pk") or request.data.get("post_id")
            if not post_id:
                return Response(
                    {"error": "Post ID is required"}, status=status.HTTP_400_BAD_REQUEST
                )

            try:
                post = BlogPost.objects.get(id=post_id)
            except BlogPost.DoesNotExist:
                raise PostNotFound()

            # Check if commenting is allowed on this post
            if not post.allow_comments:
                raise CommentOnClosedPost()

            # Check viewing permissions
            if not can_view_blog_post(request.user, post):
                raise UnauthorizedPostAccess()

            # Rate limiting check
            recent_comments = BlogComment.objects.filter(
                author=request.user,
                created_at__gte=timezone.now() - timedelta(minutes=5),
            ).count()

            if recent_comments >= 5:
                raise CommentCreationLimitExceeded()

            # Create comment
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            comment = serializer.save(
                author=request.user,
                post=post,
                status=BlogComment.CommentStatus.PENDING,  # Comments start as pending
            )

            # Send notification to post author
            if post.author != request.user:
                send_comment_notification.delay(comment.id, post.author.id)

            # Auto-approve comments from trusted users
            if (
                request.user.is_staff
                or hasattr(request.user, "userprofile")
                and request.user.userprofile.is_verified
            ):
                comment.status = BlogComment.CommentStatus.APPROVED
                comment.save()

            headers = self.get_success_headers(serializer.data)
            return Response(
                serializer.data, status=status.HTTP_201_CREATED, headers=headers
            )
        except Exception as e:
            logger.error(f"Error creating comment: {str(e)}", exc_info=True)
            if isinstance(
                e,
                (
                    PostNotFound,
                    CommentOnClosedPost,
                    UnauthorizedPostAccess,
                    CommentCreationLimitExceeded,
                ),
            ):
                raise
            return Response(
                {"error": "Failed to create comment"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Blog Comments"], responses={200: BlogCommentSerializer(many=True)}
    )
    @action(
        detail=False,
        methods=["get"],
        permission_classes=[permissions.IsAuthenticated, IsBlogModerator],
    )
    def moderation_queue(self, request):
        """Get comments pending moderation."""
        try:
            queryset = self.filter_queryset(self.get_queryset())
            page = self.paginate_queryset(queryset)

            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(
                f"Error getting comment moderation queue: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get moderation queue"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Blog Comments"],
        request=BlogCommentModerateSerializer,
        responses={200: BlogCommentSerializer},
    )
    @action(
        detail=True,
        methods=["patch"],
        permission_classes=[permissions.IsAuthenticated, IsBlogModerator],
    )
    def moderate(self, request, pk=None):
        """Moderate a comment (approve/reject/spam)."""
        try:
            comment = self.get_object()

            serializer = BlogCommentModerateSerializer(
                comment, data=request.data, partial=True, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()

            # Return updated comment
            response_serializer = BlogCommentSerializer(
                comment, context={"request": request}
            )
            return Response(response_serializer.data)
        except Exception as e:
            logger.error(f"Error moderating comment: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to moderate comment"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Blog Comments"],
        request=BulkCommentActionSerializer,
        responses={
            200: {"type": "object", "properties": {"message": {"type": "string"}}}
        },
    )
    @action(
        detail=False,
        methods=["post"],
        permission_classes=[permissions.IsAuthenticated, IsBlogModerator],
    )
    def bulk_moderate(self, request):
        """Perform bulk moderation actions on comments."""
        try:
            serializer = BulkCommentActionSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            comment_ids = serializer.validated_data["comment_ids"]
            action = serializer.validated_data["action"]
            reason = serializer.validated_data.get("reason", "")

            comments = BlogComment.objects.filter(id__in=comment_ids)
            updated_count = 0

            with transaction.atomic():
                for comment in comments:
                    if action == "approve":
                        comment.status = BlogComment.CommentStatus.APPROVED
                    elif action == "reject":
                        comment.status = BlogComment.CommentStatus.REJECTED
                    elif action == "spam":
                        comment.status = BlogComment.CommentStatus.SPAM
                    elif action == "delete":
                        comment.delete()
                        continue

                    comment.save()
                    updated_count += 1

                    # Log moderation action
                    BlogModerationLog.objects.create(
                        moderator=request.user,
                        action_type=getattr(
                            BlogModerationLog.ActionType, action.upper(), "OTHER"
                        ),
                        content_object=comment,
                        description=reason or f"Bulk {action}",
                        ip_address=request.META.get("REMOTE_ADDR"),
                        user_agent=request.META.get("HTTP_USER_AGENT", ""),
                    )

            return Response(
                {"message": f"Successfully {action}ed {updated_count} comments"}
            )
        except Exception as e:
            logger.error(f"Error in bulk comment moderation: {str(e)}", exc_info=True)
            return Response(
                {"error": "Bulk moderation failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class BlogDashboardView(APIView, BlogPermissionMixin):
    """
    API view for blog dashboard statistics.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Blog Dashboard"], responses={200: BlogDashboardStatsSerializer}
    )
    def get(self, request):
        """Get blog dashboard statistics."""
        try:
            user = request.user

            # Check if user has access to dashboard
            if not (user.is_staff or can_moderate_content(user)):
                # Return user-specific stats only
                return self._get_author_stats(request)

            # Admin/moderator dashboard stats
            cache_key = "blog_dashboard_stats"
            cached_stats = cache.get(cache_key)

            if cached_stats is None:
                stats = self._calculate_dashboard_stats()
                cache.set(cache_key, stats, 60 * 15)  # Cache for 15 minutes
                cached_stats = stats

            serializer = BlogDashboardStatsSerializer(cached_stats)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting dashboard stats: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get dashboard statistics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _calculate_dashboard_stats(self) -> Dict[str, Any]:
        """Calculate dashboard statistics."""
        # Post statistics
        total_posts = BlogPost.objects.count()
        published_posts = BlogPost.objects.filter(
            status=BlogPost.PostStatus.PUBLISHED
        ).count()
        draft_posts = BlogPost.objects.filter(status=BlogPost.PostStatus.DRAFT).count()

        # Comment statistics
        total_comments = BlogComment.objects.count()
        pending_comments = BlogComment.objects.filter(
            status=BlogComment.CommentStatus.PENDING
        ).count()

        # View statistics
        total_views = BlogView.objects.count()
        unique_visitors = BlogView.objects.values("ip_address").distinct().count()

        # Popular content
        popular_posts = BlogPost.objects.filter(
            status=BlogPost.PostStatus.PUBLISHED
        ).order_by("-views_count")[:5]

        recent_posts = BlogPost.objects.filter(
            status=BlogPost.PostStatus.PUBLISHED
        ).order_by("-published_at")[:5]

        trending_tags = BlogTag.objects.filter(usage_count__gt=0).order_by(
            "-usage_count"
        )[:10]

        top_categories = (
            BlogCategory.objects.filter(is_active=True)
            .annotate(posts_count=Count("blogpost"))
            .filter(posts_count__gt=0)
            .order_by("-posts_count")[:10]
        )

        return {
            "total_posts": total_posts,
            "published_posts": published_posts,
            "draft_posts": draft_posts,
            "total_comments": total_comments,
            "pending_comments": pending_comments,
            "total_views": total_views,
            "unique_visitors": unique_visitors,
            "popular_posts": popular_posts,
            "recent_posts": recent_posts,
            "trending_tags": trending_tags,
            "top_categories": top_categories,
        }

    def _get_author_stats(self, request):
        """Get statistics for individual authors."""
        try:
            user = request.user

            # Author-specific statistics
            user_posts = BlogPost.objects.filter(author=user)
            total_posts = user_posts.count()

            total_views = BlogView.objects.filter(post__author=user).count()
            total_reactions = BlogReaction.objects.filter(post__author=user).count()
            total_comments = BlogComment.objects.filter(post__author=user).count()

            # Followers count (if implemented)
            followers_count = 0  # Implement based on your follow system

            # Average reading time
            avg_reading_time = (
                user_posts.aggregate(avg_time=Avg("reading_time"))["avg_time"] or 0
            )

            # Engagement rate
            engagement_rate = 0
            if total_views > 0:
                engagement_rate = (
                    (total_reactions + total_comments) / total_views
                ) * 100

            # Top posts
            top_posts = user_posts.filter(
                status=BlogPost.PostStatus.PUBLISHED
            ).order_by("-views_count")[:5]

            # User badges
            badges = UserBlogBadge.objects.filter(user=user, is_visible=True)

            stats = {
                "total_posts": total_posts,
                "total_views": total_views,
                "total_reactions": total_reactions,
                "total_comments": total_comments,
                "followers_count": followers_count,
                "avg_reading_time": avg_reading_time,
                "engagement_rate": engagement_rate,
                "top_posts": top_posts,
                "badges": badges,
            }

            serializer = AuthorStatsSerializer(stats)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting author stats: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get author statistics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# Additional utility views can be added here for:
# - BlogSeriesViewSet
# - BlogSubscriptionViewSet
# - BlogReadingListViewSet
# - BlogAnalyticsViewSet
# - BlogModerationLogViewSet
# - BlogNewsletterViewSet
# - BlogBadgeViewSet
# - etc.
