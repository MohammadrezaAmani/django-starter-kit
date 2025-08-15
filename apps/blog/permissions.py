import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied

from .models import BlogModerationLog, BlogPost

logger = logging.getLogger(__name__)
User = get_user_model()


class IsBlogAuthor(permissions.BasePermission):
    """
    Permission to check if user is the author of the blog post.
    """

    def has_object_permission(self, request, view, obj):
        if hasattr(obj, "author"):
            return obj.author == request.user
        elif hasattr(obj, "post"):
            return obj.post.author == request.user
        return False


class IsBlogModerator(permissions.BasePermission):
    """
    Permission to check if user is a blog moderator.
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_staff
            or hasattr(request.user, "userprofile")
            and request.user.userprofile.role in ["moderator", "admin"]
        )

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsBlogAdmin(permissions.BasePermission):
    """
    Permission to check if user is a blog admin.
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_superuser
            or (
                hasattr(request.user, "userprofile")
                and request.user.userprofile.role == "admin"
            )
        )

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class CanViewBlogPost(permissions.BasePermission):
    """
    Permission to check if user can view a blog post based on visibility settings.
    """

    def has_object_permission(self, request, view, obj):
        # Public posts can be viewed by anyone
        if obj.visibility == BlogPost.Visibility.PUBLIC:
            return True

        # Private posts can only be viewed by the author
        if obj.visibility == BlogPost.Visibility.PRIVATE:
            return obj.author == request.user

        # Authenticated users can view posts for authenticated users
        if obj.visibility == BlogPost.Visibility.AUTHENTICATED:
            return request.user.is_authenticated

        # Draft posts can only be viewed by author and moderators
        if obj.status == BlogPost.PostStatus.DRAFT:
            return obj.author == request.user or IsBlogModerator().has_permission(
                request, view
            )

        # Published posts follow visibility rules
        if obj.status == BlogPost.PostStatus.PUBLISHED:
            return (
                obj.visibility == BlogPost.Visibility.PUBLIC
                or request.user.is_authenticated
            )

        return False


class CanEditBlogPost(permissions.BasePermission):
    """
    Permission to check if user can edit a blog post.
    """

    def has_object_permission(self, request, view, obj):
        # Authors can edit their own posts
        if obj.author == request.user:
            return True

        # Moderators and admins can edit any post
        if IsBlogModerator().has_permission(
            request, view
        ) or IsBlogAdmin().has_permission(request, view):
            return True

        return False


class CanDeleteBlogPost(permissions.BasePermission):
    """
    Permission to check if user can delete a blog post.
    """

    def has_object_permission(self, request, view, obj):
        # Authors can delete their own posts
        if obj.author == request.user:
            return True

        # Only admins can delete others' posts
        if IsBlogAdmin().has_permission(request, view):
            return True

        return False


class CanModerateBlogPost(permissions.BasePermission):
    """
    Permission to check if user can moderate a blog post (approve, reject, feature).
    """

    def has_permission(self, request, view):
        return IsBlogModerator().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class CanCommentOnPost(permissions.BasePermission):
    """
    Permission to check if user can comment on a blog post.
    """

    def has_object_permission(self, request, view, obj):
        # Check if commenting is enabled on the post
        if hasattr(obj, "allow_comments") and not obj.allow_comments:
            return False

        # Check if user is authenticated (required for comments)
        if not request.user.is_authenticated:
            return False

        # Check if user is banned from commenting
        if hasattr(request.user, "userprofile") and request.user.userprofile.is_banned:
            return False

        # Check if post allows comments based on visibility
        if hasattr(obj, "post"):
            post = obj.post
        else:
            post = obj

        return CanViewBlogPost().has_object_permission(request, view, post)


class CanEditComment(permissions.BasePermission):
    """
    Permission to check if user can edit a comment.
    """

    def has_object_permission(self, request, view, obj):
        # Users can edit their own comments within a time limit
        if obj.author == request.user:
            # Check if comment is within edit time limit (e.g., 15 minutes)
            time_limit = timezone.now() - timedelta(minutes=15)
            if obj.created_at > time_limit:
                return True

        # Moderators and admins can edit any comment
        if IsBlogModerator().has_permission(
            request, view
        ) or IsBlogAdmin().has_permission(request, view):
            return True

        return False


class CanDeleteComment(permissions.BasePermission):
    """
    Permission to check if user can delete a comment.
    """

    def has_object_permission(self, request, view, obj):
        # Users can delete their own comments
        if obj.author == request.user:
            return True

        # Post authors can delete comments on their posts
        if obj.post.author == request.user:
            return True

        # Moderators and admins can delete any comment
        if IsBlogModerator().has_permission(
            request, view
        ) or IsBlogAdmin().has_permission(request, view):
            return True

        return False


class CanManageCategories(permissions.BasePermission):
    """
    Permission to check if user can manage blog categories.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True

        return request.user.is_authenticated and (
            IsBlogModerator().has_permission(request, view)
            or IsBlogAdmin().has_permission(request, view)
        )


class CanManageTags(permissions.BasePermission):
    """
    Permission to check if user can manage blog tags.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True

        return request.user.is_authenticated


class CanViewAnalytics(permissions.BasePermission):
    """
    Permission to check if user can view blog analytics.
    """

    def has_permission(self, request, view):
        return IsBlogModerator().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        # Users can view analytics for their own posts
        if hasattr(obj, "post") and obj.post.author == request.user:
            return True

        # Moderators and admins can view all analytics
        if IsBlogModerator().has_permission(
            request, view
        ) or IsBlogAdmin().has_permission(request, view):
            return True

        return False


class CanManageNewsletter(permissions.BasePermission):
    """
    Permission to check if user can manage newsletters.
    """

    def has_permission(self, request, view):
        return IsBlogAdmin().has_permission(request, view)


class CanAccessModerationLog(permissions.BasePermission):
    """
    Permission to check if user can access moderation logs.
    """

    def has_permission(self, request, view):
        return IsBlogModerator().has_permission(request, view)


class RateLimitedBlogPermission(permissions.BasePermission):
    """
    Permission to implement rate limiting for blog operations.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        # Check for rate limiting based on user's recent activity
        recent_posts = BlogPost.objects.filter(
            author=request.user, created_at__gte=timezone.now() - timedelta(hours=1)
        ).count()

        # Limit regular users to 5 posts per hour
        max_posts_per_hour = 5
        if hasattr(request.user, "userprofile"):
            if request.user.userprofile.role in ["moderator", "admin"]:
                max_posts_per_hour = 50  # Higher limit for moderators/admins

        if recent_posts >= max_posts_per_hour:
            raise PermissionDenied("Rate limit exceeded. Please try again later.")

        return True


class CanCreateBlogSeries(permissions.BasePermission):
    """
    Permission to check if user can create blog series.
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if obj.author == request.user:
            return True

        return IsBlogModerator().has_permission(
            request, view
        ) or IsBlogAdmin().has_permission(request, view)


# Utility functions for permission checking


def can_view_blog_post(user, post):
    """
    Check if a user can view a specific blog post.
    """
    if (
        post.visibility == BlogPost.Visibility.PUBLIC
        and post.status == BlogPost.PostStatus.PUBLISHED
    ):
        return True

    if not user.is_authenticated:
        return False

    if post.author == user:
        return True

    if post.visibility == BlogPost.Visibility.PRIVATE:
        return False

    if post.visibility == BlogPost.Visibility.AUTHENTICATED and user.is_authenticated:
        return post.status == BlogPost.PostStatus.PUBLISHED

    # Check if user is moderator/admin
    if user.is_staff or (
        hasattr(user, "userprofile") and user.userprofile.role in ["moderator", "admin"]
    ):
        return True

    return False


def can_moderate_content(user):
    """
    Check if a user can moderate blog content.
    """
    return user.is_authenticated and (
        user.is_staff
        or user.is_superuser
        or (
            hasattr(user, "userprofile")
            and user.userprofile.role in ["moderator", "admin"]
        )
    )


def can_access_admin_features(user):
    """
    Check if a user can access admin features.
    """
    return user.is_authenticated and (
        user.is_superuser
        or (hasattr(user, "userprofile") and user.userprofile.role == "admin")
    )


def is_post_author(user, post):
    """
    Check if user is the author of the post.
    """
    return user.is_authenticated and post.author == user


def can_interact_with_post(user, post):
    """
    Check if user can interact with post (like, comment, share).
    """
    if not can_view_blog_post(user, post):
        return False

    if not user.is_authenticated:
        return False

    # Check if user is banned
    if hasattr(user, "userprofile") and user.userprofile.is_banned:
        return False

    return True


class BlogPermissionMixin:
    """
    Mixin to provide common permission methods for blog views.
    """

    def check_blog_permissions(self, request, obj=None, action=None):
        """
        Check blog-specific permissions based on action.
        """
        if not request.user.is_authenticated:
            if action in ["create", "update", "destroy", "comment", "like"]:
                raise PermissionDenied("Authentication required")

        if obj and action:
            if action == "view":
                if not can_view_blog_post(request.user, obj):
                    raise PermissionDenied("Cannot view this post")
            elif action == "edit":
                if not (
                    is_post_author(request.user, obj)
                    or can_moderate_content(request.user)
                ):
                    raise PermissionDenied("Cannot edit this post")
            elif action == "delete":
                if not (
                    is_post_author(request.user, obj)
                    or can_access_admin_features(request.user)
                ):
                    raise PermissionDenied("Cannot delete this post")
            elif action == "moderate":
                if not can_moderate_content(request.user):
                    raise PermissionDenied("Cannot moderate content")

    def log_permission_check(self, request, action, obj=None, granted=True):
        """
        Log permission checks for audit purposes.
        """
        try:
            BlogModerationLog.objects.create(
                moderator=request.user if request.user.is_authenticated else None,
                action_type=getattr(
                    BlogModerationLog.ActionType, action.upper(), "OTHER"
                ),
                content_object=obj,
                description=f"Permission {'granted' if granted else 'denied'} for {action}",
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except Exception as e:
            logger.error(f"Failed to log permission check: {e}")
