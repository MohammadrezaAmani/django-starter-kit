from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers

from .views import (
    BlogCategoryViewSet,
    BlogCommentViewSet,
    BlogDashboardView,
    BlogPostViewSet,
    BlogTagViewSet,
)

app_name = "blog"

# Main router
router = DefaultRouter()
router.register("posts", BlogPostViewSet, basename="posts")
router.register("categories", BlogCategoryViewSet, basename="categories")
router.register("tags", BlogTagViewSet, basename="tags")
router.register("comments", BlogCommentViewSet, basename="comments")

# Nested routers for post-specific resources
posts_router = routers.NestedDefaultRouter(router, "posts", lookup="post")
posts_router.register("comments", BlogCommentViewSet, basename="post-comments")

# Categories nested router
categories_router = routers.NestedDefaultRouter(router, "categories", lookup="category")

# Tags nested router
tags_router = routers.NestedDefaultRouter(router, "tags", lookup="tag")

urlpatterns = [
    # Main API routes
    path("api/", include(router.urls)),
    path("api/", include(posts_router.urls)),
    path("api/", include(categories_router.urls)),
    path("api/", include(tags_router.urls)),
    # Dashboard
    path("api/dashboard/", BlogDashboardView.as_view(), name="dashboard"),
    # Additional custom endpoints
    path(
        "api/posts/trending/",
        BlogPostViewSet.as_view({"get": "trending"}),
        name="trending-posts",
    ),
    path(
        "api/posts/featured/",
        BlogPostViewSet.as_view({"get": "featured"}),
        name="featured-posts",
    ),
    path(
        "api/posts/popular/",
        BlogPostViewSet.as_view({"get": "popular"}),
        name="popular-posts",
    ),
    path(
        "api/posts/search/",
        BlogPostViewSet.as_view({"get": "search"}),
        name="search-posts",
    ),
    path(
        "api/posts/sitemap/",
        BlogPostViewSet.as_view({"get": "sitemap"}),
        name="sitemap",
    ),
    path(
        "api/posts/my-posts/",
        BlogPostViewSet.as_view({"get": "my_posts"}),
        name="my-posts",
    ),
    path(
        "api/posts/my-drafts/",
        BlogPostViewSet.as_view({"get": "my_drafts"}),
        name="my-drafts",
    ),
    path(
        "api/posts/moderation-queue/",
        BlogPostViewSet.as_view({"get": "moderation_queue"}),
        name="moderation-queue",
    ),
    path(
        "api/posts/bulk-moderate/",
        BlogPostViewSet.as_view({"post": "bulk_moderate"}),
        name="bulk-moderate-posts",
    ),
    # Post-specific actions
    path(
        "api/posts/<int:pk>/react/",
        BlogPostViewSet.as_view({"post": "react"}),
        name="react-to-post",
    ),
    path(
        "api/posts/<int:pk>/unreact/",
        BlogPostViewSet.as_view({"delete": "unreact"}),
        name="unreact-to-post",
    ),
    path(
        "api/posts/<int:pk>/analytics/",
        BlogPostViewSet.as_view({"get": "analytics"}),
        name="post-analytics",
    ),
    path(
        "api/posts/<int:pk>/moderate/",
        BlogPostViewSet.as_view({"patch": "moderate"}),
        name="moderate-post",
    ),
    # Category-specific actions
    path(
        "api/categories/tree/",
        BlogCategoryViewSet.as_view({"get": "tree"}),
        name="category-tree",
    ),
    path(
        "api/categories/stats/",
        BlogCategoryViewSet.as_view({"get": "stats"}),
        name="category-stats",
    ),
    path(
        "api/categories/<int:pk>/posts/",
        BlogCategoryViewSet.as_view({"get": "posts"}),
        name="category-posts",
    ),
    # Tag-specific actions
    path(
        "api/tags/popular/",
        BlogTagViewSet.as_view({"get": "popular"}),
        name="popular-tags",
    ),
    path(
        "api/tags/trending/",
        BlogTagViewSet.as_view({"get": "trending"}),
        name="trending-tags",
    ),
    path(
        "api/tags/<int:pk>/posts/",
        BlogTagViewSet.as_view({"get": "posts"}),
        name="tag-posts",
    ),
    # Comment-specific actions
    path(
        "api/comments/moderation-queue/",
        BlogCommentViewSet.as_view({"get": "moderation_queue"}),
        name="comment-moderation-queue",
    ),
    path(
        "api/comments/bulk-moderate/",
        BlogCommentViewSet.as_view({"post": "bulk_moderate"}),
        name="bulk-moderate-comments",
    ),
    path(
        "api/comments/<int:pk>/moderate/",
        BlogCommentViewSet.as_view({"patch": "moderate"}),
        name="moderate-comment",
    ),
]
