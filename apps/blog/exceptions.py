import logging

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    NotFound,
    PermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class BlogBaseException(APIException):
    """Base exception for all blog-related errors."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "A blog error occurred."
    default_code = "blog_error"


class PostNotFound(NotFound):
    """Exception raised when a blog post is not found."""

    default_detail = "Blog post not found."
    default_code = "post_not_found"


class CategoryNotFound(NotFound):
    """Exception raised when a blog category is not found."""

    default_detail = "Blog category not found."
    default_code = "category_not_found"


class TagNotFound(NotFound):
    """Exception raised when a blog tag is not found."""

    default_detail = "Blog tag not found."
    default_code = "tag_not_found"


class CommentNotFound(NotFound):
    """Exception raised when a blog comment is not found."""

    default_detail = "Blog comment not found."
    default_code = "comment_not_found"


class SeriesNotFound(NotFound):
    """Exception raised when a blog series is not found."""

    default_detail = "Blog series not found."
    default_code = "series_not_found"


class UnauthorizedPostAccess(PermissionDenied):
    """Exception raised when user tries to access a post they don't have permission for."""

    default_detail = "You don't have permission to access this post."
    default_code = "unauthorized_post_access"


class UnauthorizedPostEdit(PermissionDenied):
    """Exception raised when user tries to edit a post they don't own."""

    default_detail = "You don't have permission to edit this post."
    default_code = "unauthorized_post_edit"


class UnauthorizedPostDelete(PermissionDenied):
    """Exception raised when user tries to delete a post they don't own."""

    default_detail = "You don't have permission to delete this post."
    default_code = "unauthorized_post_delete"


class UnauthorizedCommentEdit(PermissionDenied):
    """Exception raised when user tries to edit a comment they don't own."""

    default_detail = "You don't have permission to edit this comment."
    default_code = "unauthorized_comment_edit"


class UnauthorizedCommentDelete(PermissionDenied):
    """Exception raised when user tries to delete a comment they don't own."""

    default_detail = "You don't have permission to delete this comment."
    default_code = "unauthorized_comment_delete"


class UnauthorizedModerationAccess(PermissionDenied):
    """Exception raised when user tries to access moderation features without permission."""

    default_detail = "You don't have permission to access moderation features."
    default_code = "unauthorized_moderation_access"


class PostAlreadyPublished(ValidationError):
    """Exception raised when trying to publish an already published post."""

    default_detail = "This post is already published."
    default_code = "post_already_published"


class PostAlreadyDraft(ValidationError):
    """Exception raised when trying to make a published post a draft."""

    default_detail = "Cannot revert published post to draft."
    default_code = "post_already_draft"


class InvalidPostStatus(ValidationError):
    """Exception raised when an invalid post status is provided."""

    default_detail = "Invalid post status."
    default_code = "invalid_post_status"


class InvalidPostVisibility(ValidationError):
    """Exception raised when an invalid post visibility is provided."""

    default_detail = "Invalid post visibility setting."
    default_code = "invalid_post_visibility"


class InvalidCommentStatus(ValidationError):
    """Exception raised when an invalid comment status is provided."""

    default_detail = "Invalid comment status."
    default_code = "invalid_comment_status"


class CommentOnClosedPost(ValidationError):
    """Exception raised when trying to comment on a post that doesn't allow comments."""

    default_detail = "Comments are not allowed on this post."
    default_code = "comment_on_closed_post"


class SelfReactionError(ValidationError):
    """Exception raised when user tries to react to their own content."""

    default_detail = "You cannot react to your own content."
    default_code = "self_reaction_error"


class DuplicateReactionError(ValidationError):
    """Exception raised when user tries to react twice to the same content."""

    default_detail = "You have already reacted to this content."
    default_code = "duplicate_reaction_error"


class MaxCategoriesExceeded(ValidationError):
    """Exception raised when trying to add more categories than allowed."""

    default_detail = "Maximum number of categories exceeded."
    default_code = "max_categories_exceeded"


class MaxTagsExceeded(ValidationError):
    """Exception raised when trying to add more tags than allowed."""

    default_detail = "Maximum number of tags exceeded."
    default_code = "max_tags_exceeded"


class InvalidSlug(ValidationError):
    """Exception raised when an invalid or duplicate slug is provided."""

    default_detail = "Invalid or duplicate slug provided."
    default_code = "invalid_slug"


class ContentTooLong(ValidationError):
    """Exception raised when content exceeds maximum length."""

    default_detail = "Content exceeds maximum allowed length."
    default_code = "content_too_long"


class ContentTooShort(ValidationError):
    """Exception raised when content is below minimum length."""

    default_detail = "Content is below minimum required length."
    default_code = "content_too_short"


class InvalidFileType(ValidationError):
    """Exception raised when an invalid file type is uploaded."""

    default_detail = "Invalid file type. Please upload a valid file."
    default_code = "invalid_file_type"


class FileSizeExceeded(ValidationError):
    """Exception raised when uploaded file exceeds size limit."""

    default_detail = "File size exceeds the maximum allowed limit."
    default_code = "file_size_exceeded"


class TooManyFiles(ValidationError):
    """Exception raised when too many files are uploaded."""

    default_detail = "Maximum number of files exceeded."
    default_code = "too_many_files"


class BlogRateLimitExceeded(Throttled):
    """Exception raised when blog-specific rate limits are exceeded."""

    default_detail = "Blog rate limit exceeded. Please try again later."
    default_code = "blog_rate_limit_exceeded"


class PostCreationLimitExceeded(BlogRateLimitExceeded):
    """Exception raised when post creation limit is exceeded."""

    default_detail = "Post creation limit exceeded. Please try again later."
    default_code = "post_creation_limit_exceeded"


class CommentCreationLimitExceeded(BlogRateLimitExceeded):
    """Exception raised when comment creation limit is exceeded."""

    default_detail = "Comment creation limit exceeded. Please try again later."
    default_code = "comment_creation_limit_exceeded"


class ReactionLimitExceeded(BlogRateLimitExceeded):
    """Exception raised when reaction limit is exceeded."""

    default_detail = "Reaction limit exceeded. Please try again later."
    default_code = "reaction_limit_exceeded"


class SubscriptionError(BlogBaseException):
    """Exception raised for subscription-related errors."""

    default_detail = "Subscription error occurred."
    default_code = "subscription_error"


class AlreadySubscribed(SubscriptionError):
    """Exception raised when user tries to subscribe to something they're already subscribed to."""

    default_detail = "You are already subscribed."
    default_code = "already_subscribed"


class NotSubscribed(SubscriptionError):
    """Exception raised when user tries to unsubscribe from something they're not subscribed to."""

    default_detail = "You are not subscribed."
    default_code = "not_subscribed"


class InvalidSubscriptionType(SubscriptionError):
    """Exception raised when an invalid subscription type is provided."""

    default_detail = "Invalid subscription type."
    default_code = "invalid_subscription_type"


class AnalyticsError(BlogBaseException):
    """Exception raised for analytics-related errors."""

    default_detail = "Analytics error occurred."
    default_code = "analytics_error"


class AnalyticsDataNotAvailable(AnalyticsError):
    """Exception raised when analytics data is not available."""

    default_detail = "Analytics data is not available for this content."
    default_code = "analytics_data_not_available"


class NewsletterError(BlogBaseException):
    """Exception raised for newsletter-related errors."""

    default_detail = "Newsletter error occurred."
    default_code = "newsletter_error"


class NewsletterAlreadySent(NewsletterError):
    """Exception raised when trying to send an already sent newsletter."""

    default_detail = "This newsletter has already been sent."
    default_code = "newsletter_already_sent"


class NewsletterNotReady(NewsletterError):
    """Exception raised when trying to send a newsletter that's not ready."""

    default_detail = "Newsletter is not ready to be sent."
    default_code = "newsletter_not_ready"


class ModerationError(BlogBaseException):
    """Exception raised for moderation-related errors."""

    default_detail = "Moderation error occurred."
    default_code = "moderation_error"


class ContentAlreadyModerated(ModerationError):
    """Exception raised when trying to moderate already moderated content."""

    default_detail = "This content has already been moderated."
    default_code = "content_already_moderated"


class InvalidModerationAction(ModerationError):
    """Exception raised when an invalid moderation action is requested."""

    default_detail = "Invalid moderation action."
    default_code = "invalid_moderation_action"


class SeriesError(BlogBaseException):
    """Exception raised for series-related errors."""

    default_detail = "Blog series error occurred."
    default_code = "series_error"


class PostAlreadyInSeries(SeriesError):
    """Exception raised when trying to add a post that's already in the series."""

    default_detail = "This post is already in the series."
    default_code = "post_already_in_series"


class PostNotInSeries(SeriesError):
    """Exception raised when trying to remove a post that's not in the series."""

    default_detail = "This post is not in the series."
    default_code = "post_not_in_series"


class InvalidSeriesOrder(SeriesError):
    """Exception raised when an invalid series order is provided."""

    default_detail = "Invalid series order."
    default_code = "invalid_series_order"


class MaxSeriesPostsExceeded(SeriesError):
    """Exception raised when maximum number of posts in series is exceeded."""

    default_detail = "Maximum number of posts in series exceeded."
    default_code = "max_series_posts_exceeded"


class BadgeError(BlogBaseException):
    """Exception raised for badge-related errors."""

    default_detail = "Badge error occurred."
    default_code = "badge_error"


class BadgeAlreadyEarned(BadgeError):
    """Exception raised when trying to award a badge that's already earned."""

    default_detail = "This badge has already been earned."
    default_code = "badge_already_earned"


class BadgeNotEarned(BadgeError):
    """Exception raised when trying to access a badge that hasn't been earned."""

    default_detail = "This badge has not been earned."
    default_code = "badge_not_earned"


class InvalidBadgeType(BadgeError):
    """Exception raised when an invalid badge type is provided."""

    default_detail = "Invalid badge type."
    default_code = "invalid_badge_type"


class ReadingListError(BlogBaseException):
    """Exception raised for reading list-related errors."""

    default_detail = "Reading list error occurred."
    default_code = "reading_list_error"


class PostAlreadyInReadingList(ReadingListError):
    """Exception raised when trying to add a post that's already in the reading list."""

    default_detail = "This post is already in your reading list."
    default_code = "post_already_in_reading_list"


class PostNotInReadingList(ReadingListError):
    """Exception raised when trying to remove a post that's not in the reading list."""

    default_detail = "This post is not in your reading list."
    default_code = "post_not_in_reading_list"


class MaxReadingListSizeExceeded(ReadingListError):
    """Exception raised when reading list size limit is exceeded."""

    default_detail = "Reading list size limit exceeded."
    default_code = "max_reading_list_size_exceeded"


class PrivateReadingListAccess(ReadingListError):
    """Exception raised when trying to access a private reading list."""

    default_detail = "This reading list is private."
    default_code = "private_reading_list_access"


def custom_blog_exception_handler(exc, context):
    """
    Custom exception handler for blog-specific exceptions.
    """
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)

    if response is not None:
        # Log the exception
        request = context.get("request")
        user = request.user if request and hasattr(request, "user") else None

        logger.error(
            f"Blog API Exception: {exc.__class__.__name__} - {str(exc)}",
            extra={
                "user": user.id if user and user.is_authenticated else None,
                "path": request.path if request else None,
                "method": request.method if request else None,
                "status_code": response.status_code,
                "exception_class": exc.__class__.__name__,
            },
            exc_info=True,
        )

        # Customize error response format
        custom_response_data = {
            "error": {
                "code": getattr(exc, "default_code", "unknown_error"),
                "message": str(exc),
                "status_code": response.status_code,
                "timestamp": timezone.now().isoformat(),
            }
        }

        # Add additional context for specific exceptions
        if isinstance(exc, BlogRateLimitExceeded):
            custom_response_data["error"]["retry_after"] = getattr(exc, "wait", None)

        if isinstance(exc, ValidationError):
            custom_response_data["error"]["field_errors"] = response.data

        if isinstance(exc, PermissionDenied):
            custom_response_data["error"]["required_permissions"] = getattr(
                exc, "required_permissions", None
            )

        response.data = custom_response_data

    return response


# Utility functions for raising exceptions with context


def raise_post_not_found(post_id=None):
    """Raise PostNotFound with optional post ID context."""
    detail = (
        f"Blog post with ID {post_id} not found." if post_id else "Blog post not found."
    )
    raise PostNotFound(detail=detail)


def raise_unauthorized_access(resource_type, action, user=None):
    """Raise unauthorized access exception with context."""
    detail = f"You don't have permission to {action} this {resource_type}."
    if user and hasattr(user, "userprofile"):
        detail += f" Current role: {getattr(user.userprofile, 'role', 'user')}"
    raise PermissionDenied(detail=detail)


def raise_rate_limit_exceeded(resource_type, limit, timeframe):
    """Raise rate limit exceeded exception with context."""
    detail = f"Rate limit exceeded for {resource_type}. Limit: {limit} per {timeframe}."
    raise BlogRateLimitExceeded(detail=detail)


def raise_validation_error(field, message, code=None):
    """Raise validation error for specific field."""
    raise ValidationError({field: [message]}, code=code)


def raise_content_error(content_type, issue, min_length=None, max_length=None):
    """Raise content-related validation error with context."""
    if issue == "too_long" and max_length:
        detail = (
            f"{content_type} content exceeds maximum length of {max_length} characters."
        )
        raise ContentTooLong(detail=detail)
    elif issue == "too_short" and min_length:
        detail = f"{content_type} content is below minimum length of {min_length} characters."
        raise ContentTooShort(detail=detail)
    else:
        raise ValidationError(f"Invalid {content_type} content: {issue}")


# Exception mapping for common Django exceptions
EXCEPTION_MAPPING = {
    ObjectDoesNotExist: NotFound,
    IntegrityError: ValidationError,
}


def map_django_exception(exc):
    """Map Django exceptions to DRF exceptions."""
    for django_exc, drf_exc in EXCEPTION_MAPPING.items():
        if isinstance(exc, django_exc):
            return drf_exc(detail=str(exc))
    return exc
