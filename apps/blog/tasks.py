import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from celery import shared_task
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.mail import send_mail, send_mass_mail
from django.db import transaction
from django.db.models import Count, F
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from apps.notifications.tasks import send_notification as send_user_notification

from .models import (
    BlogAnalytics,
    BlogBadge,
    BlogCategory,
    BlogComment,
    BlogModerationLog,
    BlogNewsletter,
    BlogPost,
    BlogSubscription,
    BlogTag,
    BlogView,
    UserBlogBadge,
)

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task(bind=True, max_retries=3)
def update_post_analytics(
    self, post_id: int, user_id: Optional[int] = None, action: str = "view", **kwargs
):
    """
    Update post analytics data.

    Args:
        post_id: Blog post ID
        user_id: User ID (None for anonymous users)
        action: Type of action ('view', 'reaction', 'comment', 'share')
        **kwargs: Additional data like ip_address, user_agent, session_duration
    """
    try:
        with transaction.atomic():
            post = BlogPost.objects.get(id=post_id)

            # Get or create analytics record
            analytics, created = BlogAnalytics.objects.get_or_create(
                post=post,
                defaults={
                    "views_count": 0,
                    "unique_views_count": 0,
                    "shares_count": 0,
                    "time_spent_total": 0,
                    "time_spent_average": 0,
                    "last_updated": timezone.now(),
                },
            )

            if action == "view":
                # Create view record
                view_data = {
                    "post": post,
                    "ip_address": kwargs.get("ip_address", ""),
                    "user_agent": kwargs.get("user_agent", ""),
                    "referrer": kwargs.get("referrer", ""),
                    "session_duration": kwargs.get("session_duration", 0),
                    "viewed_at": timezone.now(),
                }

                if user_id:
                    user = User.objects.get(id=user_id)
                    view_data["user"] = user

                # Check if this is a unique view (same IP/user in last hour)
                is_unique = True
                one_hour_ago = timezone.now() - timedelta(hours=1)

                if user_id:
                    existing_view = BlogView.objects.filter(
                        post=post, user_id=user_id, viewed_at__gte=one_hour_ago
                    ).exists()
                else:
                    existing_view = BlogView.objects.filter(
                        post=post,
                        ip_address=kwargs.get("ip_address", ""),
                        viewed_at__gte=one_hour_ago,
                    ).exists()

                if existing_view:
                    is_unique = False

                BlogView.objects.create(**view_data)

                # Update analytics
                analytics.views_count = F("views_count") + 1
                if is_unique:
                    analytics.unique_views_count = F("unique_views_count") + 1

                # Update average time spent
                if kwargs.get("session_duration", 0) > 0:
                    analytics.time_spent_total = (
                        F("time_spent_total") + kwargs["session_duration"]
                    )
                    analytics.save()
                    analytics.refresh_from_db()
                    analytics.time_spent_average = (
                        analytics.time_spent_total / analytics.views_count
                    )

                analytics.save()

                # Update post view count
                post.views_count = F("views_count") + 1
                post.save()

            elif action == "share":
                analytics.shares_count = F("shares_count") + 1
                analytics.save()

            elif action in ["reaction", "comment"]:
                # These are handled by their respective models, just update timestamp
                analytics.last_updated = timezone.now()
                analytics.save()

            # Update metrics
            analytics.update_metrics()

            # Update trending status
            update_trending_posts.delay()

            logger.info(f"Updated analytics for post {post_id}, action: {action}")

    except BlogPost.DoesNotExist:
        logger.error(f"Post {post_id} not found for analytics update")
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found for analytics update")
    except Exception as exc:
        logger.error(f"Error updating post analytics: {exc}")
        self.retry(countdown=60, exc=exc)


@shared_task(bind=True, max_retries=3)
def send_comment_notification(self, comment_id: int, recipient_id: int):
    """
    Send notification when someone comments on a post.

    Args:
        comment_id: Comment ID
        recipient_id: User ID to notify (usually post author)
    """
    try:
        comment = BlogComment.objects.select_related("author", "post").get(
            id=comment_id
        )
        recipient = User.objects.get(id=recipient_id)

        # Don't send notification if commenter is the recipient
        if comment.author == recipient:
            return

        # Check if recipient wants comment notifications
        subscription = BlogSubscription.objects.filter(
            user=recipient,
            subscription_type=BlogSubscription.SubscriptionType.COMMENTS,
            is_active=True,
        ).first()

        if not subscription:
            return

        # Create notification
        notification_data = {
            "recipient": recipient,
            "sender": comment.author,
            "notification_type": "blog_comment",
            "title": "New comment on your post",
            "message": f'{comment.author.get_full_name()} commented on "{comment.post.title}"',
            "data": {
                "comment_id": comment.id,
                "post_id": comment.post.id,
                "post_slug": comment.post.slug,
            },
        }

        # Send in-app notification
        send_user_notification.delay(notification_data)

        # Send email if user prefers email notifications
        if subscription.notification_frequency in [
            BlogSubscription.NotificationFrequency.IMMEDIATE,
            BlogSubscription.NotificationFrequency.DAILY,
        ]:
            send_comment_email_notification.delay(comment_id, recipient_id)

        logger.info(
            f"Sent comment notification for comment {comment_id} to user {recipient_id}"
        )

    except (BlogComment.DoesNotExist, User.DoesNotExist) as e:
        logger.error(f"Error sending comment notification: {e}")
    except Exception as exc:
        logger.error(f"Error sending comment notification: {exc}")
        self.retry(countdown=60, exc=exc)


@shared_task(bind=True, max_retries=3)
def send_comment_email_notification(self, comment_id: int, recipient_id: int):
    """Send email notification for new comment."""
    try:
        comment = BlogComment.objects.select_related("author", "post").get(
            id=comment_id
        )
        recipient = User.objects.get(id=recipient_id)

        subject = f'New comment on "{comment.post.title}"'

        context = {
            "recipient": recipient,
            "comment": comment,
            "post": comment.post,
            "commenter": comment.author,
            "comment_url": f"/blog/{comment.post.slug}#comment-{comment.id}",
        }

        html_message = render_to_string("blog/emails/new_comment.html", context)
        plain_message = strip_tags(html_message)

        send_mail(
            subject=subject,
            message=plain_message,
            from_email="noreply@yourdomain.com",
            recipient_list=[recipient.email],
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(f"Sent comment email notification to {recipient.email}")

    except Exception as exc:
        logger.error(f"Error sending comment email: {exc}")
        self.retry(countdown=60, exc=exc)


@shared_task(bind=True, max_retries=3)
def update_trending_posts(self):
    """Update trending posts based on recent engagement."""
    try:
        # Calculate trending score for posts from the last 7 days
        week_ago = timezone.now() - timedelta(days=7)

        trending_posts = (
            BlogPost.objects.filter(
                status=BlogPost.PostStatus.PUBLISHED, published_at__gte=week_ago
            )
            .annotate(
                trending_score=(
                    F("views_count") * 1
                    + F("reactions_count") * 2
                    + F("comments_count") * 3
                )
            )
            .filter(trending_score__gt=10)
        )  # Minimum threshold

        # Update trending status
        BlogPost.objects.update(is_trending=False)

        # Mark top posts as trending
        top_trending = trending_posts.order_by("-trending_score")[:20]
        post_ids = [post.id for post in top_trending]

        BlogPost.objects.filter(id__in=post_ids).update(is_trending=True)

        # Cache trending posts
        cache.delete("blog_trending_posts")

        logger.info(f"Updated {len(post_ids)} trending posts")

    except Exception as exc:
        logger.error(f"Error updating trending posts: {exc}")
        self.retry(countdown=60, exc=exc)


@shared_task(bind=True, max_retries=3)
def update_user_badge_progress(self, user_id: int, action: str):
    """
    Update user badge progress based on actions.

    Args:
        user_id: User ID
        action: Action type (post_created, comment_made, etc.)
    """
    try:
        user = User.objects.get(id=user_id)

        # Get all active badges
        badges = BlogBadge.objects.filter(is_active=True)

        for badge in badges:
            criteria = badge.criteria or {}

            # Check badge criteria based on action
            if (
                action == "post_created"
                and badge.badge_type == BlogBadge.BadgeType.AUTHOR
            ):
                posts_count = BlogPost.objects.filter(
                    author=user, status=BlogPost.PostStatus.PUBLISHED
                ).count()

                required_posts = criteria.get("posts_required", 0)
                if posts_count >= required_posts:
                    UserBlogBadge.objects.get_or_create(
                        user=user, badge=badge, defaults={"earned_at": timezone.now()}
                    )

            elif (
                action == "comment_made"
                and badge.badge_type == BlogBadge.BadgeType.COMMENTER
            ):
                comments_count = BlogComment.objects.filter(
                    author=user, status=BlogComment.CommentStatus.APPROVED
                ).count()

                required_comments = criteria.get("comments_required", 0)
                if comments_count >= required_comments:
                    UserBlogBadge.objects.get_or_create(
                        user=user, badge=badge, defaults={"earned_at": timezone.now()}
                    )

            elif (
                action == "view_received"
                and badge.badge_type == BlogBadge.BadgeType.POPULAR
            ):
                total_views = BlogView.objects.filter(post__author=user).count()

                required_views = criteria.get("views_required", 0)
                if total_views >= required_views:
                    UserBlogBadge.objects.get_or_create(
                        user=user, badge=badge, defaults={"earned_at": timezone.now()}
                    )

        logger.info(f"Updated badge progress for user {user_id}, action: {action}")

    except User.DoesNotExist:
        logger.error(f"User {user_id} not found for badge update")
    except Exception as exc:
        logger.error(f"Error updating user badges: {exc}")
        self.retry(countdown=60, exc=exc)


@shared_task(bind=True, max_retries=3)
def update_tag_usage_count(self, tag_id: int):
    """Update tag usage count."""
    try:
        tag = BlogTag.objects.get(id=tag_id)

        usage_count = BlogPost.objects.filter(
            tags=tag, status=BlogPost.PostStatus.PUBLISHED
        ).count()

        tag.usage_count = usage_count
        tag.save(update_fields=["usage_count"])

        logger.info(f"Updated usage count for tag {tag.name}: {usage_count}")

    except BlogTag.DoesNotExist:
        logger.error(f"Tag {tag_id} not found")
    except Exception as exc:
        logger.error(f"Error updating tag usage: {exc}")
        self.retry(countdown=60, exc=exc)


@shared_task(bind=True, max_retries=3)
def update_category_post_count(self, category_id: int):
    """Update category post count."""
    try:
        category = BlogCategory.objects.get(id=category_id)

        posts_count = BlogPost.objects.filter(
            categories=category, status=BlogPost.PostStatus.PUBLISHED
        ).count()

        # Update the category's post count (if you have this field)
        # category.posts_count = posts_count
        # category.save(update_fields=['posts_count'])

        logger.info(f"Updated post count for category {category.name}: {posts_count}")

    except BlogCategory.DoesNotExist:
        logger.error(f"Category {category_id} not found")
    except Exception as exc:
        logger.error(f"Error updating category post count: {exc}")
        self.retry(countdown=60, exc=exc)


@shared_task(bind=True, max_retries=3)
def process_newsletter_sending(self, newsletter_id: int):
    """
    Process newsletter sending to subscribers.

    Args:
        newsletter_id: Newsletter ID to send
    """
    try:
        newsletter = BlogNewsletter.objects.get(id=newsletter_id)

        if newsletter.status != BlogNewsletter.NewsletterStatus.READY:
            logger.warning(f"Newsletter {newsletter_id} is not ready for sending")
            return

        # Get active subscribers
        subscribers = BlogSubscription.objects.filter(
            subscription_type=BlogSubscription.SubscriptionType.NEWSLETTER,
            is_active=True,
        ).select_related("user")

        if not subscribers.exists():
            logger.warning(f"No subscribers found for newsletter {newsletter_id}")
            return

        # Update newsletter status
        newsletter.status = BlogNewsletter.NewsletterStatus.SENDING
        newsletter.save()

        # Prepare email data
        messages = []
        for subscription in subscribers:
            user = subscription.user

            # Personalize newsletter content
            context = {
                "user": user,
                "newsletter": newsletter,
                "unsubscribe_url": f"/blog/unsubscribe/{subscription.id}/",
            }

            html_content = render_to_string("blog/emails/newsletter.html", context)
            plain_content = strip_tags(html_content)

            messages.append(
                (
                    newsletter.subject,
                    plain_content,
                    "noreply@yourdomain.com",
                    [user.email],
                )
            )

        # Send emails in batches
        batch_size = 100
        sent_count = 0

        for i in range(0, len(messages), batch_size):
            batch = messages[i : i + batch_size]
            try:
                send_mass_mail(batch, fail_silently=False)
                sent_count += len(batch)
                logger.info(
                    f"Sent newsletter batch {i // batch_size + 1}, {len(batch)} emails"
                )
            except Exception as e:
                logger.error(f"Error sending newsletter batch: {e}")

        # Update newsletter status
        newsletter.status = BlogNewsletter.NewsletterStatus.SENT
        newsletter.sent_at = timezone.now()
        newsletter.save()

        logger.info(f"Newsletter {newsletter_id} sent to {sent_count} subscribers")

    except BlogNewsletter.DoesNotExist:
        logger.error(f"Newsletter {newsletter_id} not found")
    except Exception as exc:
        logger.error(f"Error processing newsletter: {exc}")
        self.retry(countdown=300, exc=exc)  # Retry after 5 minutes


@shared_task(bind=True, max_retries=3)
def cleanup_old_analytics(self):
    """Clean up old analytics data to maintain performance."""
    try:
        # Delete view records older than 1 year
        one_year_ago = timezone.now() - timedelta(days=365)
        old_views = BlogView.objects.filter(viewed_at__lt=one_year_ago)
        views_count = old_views.count()
        old_views.delete()

        # Delete moderation logs older than 2 years
        two_years_ago = timezone.now() - timedelta(days=730)
        old_logs = BlogModerationLog.objects.filter(created_at__lt=two_years_ago)
        logs_count = old_logs.count()
        old_logs.delete()

        logger.info(f"Cleaned up {views_count} old views and {logs_count} old logs")

    except Exception as exc:
        logger.error(f"Error cleaning up old analytics: {exc}")
        self.retry(countdown=300, exc=exc)


@shared_task(bind=True, max_retries=3)
def update_search_index(self, post_id: int):
    """
    Update search index for a blog post.
    This is a placeholder for search engine integration (Elasticsearch, etc.)
    """
    try:
        BlogPost.objects.get(id=post_id)

        # Here you would update your search index
        # For example, with Elasticsearch:
        # es_client.index(
        #     index='blog_posts',
        #     id=post.id,
        #     body={
        #         'title': post.title,
        #         'content': post.content,
        #         'author': post.author.get_full_name(),
        #         'categories': [cat.name for cat in post.categories.all()],
        #         'tags': [tag.name for tag in post.tags.all()],
        #         'published_at': post.published_at
        #     }
        # )

        logger.info(f"Updated search index for post {post_id}")

    except BlogPost.DoesNotExist:
        logger.error(f"Post {post_id} not found for search index update")
    except Exception as exc:
        logger.error(f"Error updating search index: {exc}")
        self.retry(countdown=60, exc=exc)


@shared_task(bind=True, max_retries=3)
def generate_sitemap(self):
    """Generate XML sitemap for blog posts."""
    try:
        posts = (
            BlogPost.objects.filter(
                status=BlogPost.PostStatus.PUBLISHED,
                visibility=BlogPost.Visibility.PUBLIC,
            )
            .values("slug", "updated_at")
            .order_by("-updated_at")
        )

        # Generate sitemap XML
        sitemap_data = {"posts": posts, "last_updated": timezone.now()}

        # Cache sitemap data
        cache.set("blog_sitemap", sitemap_data, 60 * 60 * 24)  # Cache for 24 hours

        logger.info(f"Generated sitemap with {len(posts)} posts")

    except Exception as exc:
        logger.error(f"Error generating sitemap: {exc}")
        self.retry(countdown=300, exc=exc)


@shared_task(bind=True, max_retries=3)
def send_weekly_digest(self):
    """Send weekly digest to subscribers."""
    try:
        # Get subscribers for weekly digest
        weekly_subscribers = BlogSubscription.objects.filter(
            subscription_type=BlogSubscription.SubscriptionType.WEEKLY_DIGEST,
            notification_frequency=BlogSubscription.NotificationFrequency.WEEKLY,
            is_active=True,
        ).select_related("user")

        if not weekly_subscribers.exists():
            logger.info("No weekly digest subscribers found")
            return

        # Get top posts from the last week
        week_ago = timezone.now() - timedelta(days=7)
        top_posts = BlogPost.objects.filter(
            status=BlogPost.PostStatus.PUBLISHED,
            visibility=BlogPost.Visibility.PUBLIC,
            published_at__gte=week_ago,
        ).order_by("-views_count", "-reactions_count")[:10]

        if not top_posts.exists():
            logger.info("No posts found for weekly digest")
            return

        # Send digest emails
        messages = []
        for subscription in weekly_subscribers:
            user = subscription.user

            context = {
                "user": user,
                "posts": top_posts,
                "week_start": week_ago,
                "unsubscribe_url": f"/blog/unsubscribe/{subscription.id}/",
            }

            subject = (
                f"Your Weekly Blog Digest - {timezone.now().strftime('%B %d, %Y')}"
            )
            html_content = render_to_string("blog/emails/weekly_digest.html", context)
            plain_content = strip_tags(html_content)

            messages.append(
                (subject, plain_content, "noreply@yourdomain.com", [user.email])
            )

        # Send emails in batches
        batch_size = 50
        sent_count = 0

        for i in range(0, len(messages), batch_size):
            batch = messages[i : i + batch_size]
            try:
                send_mass_mail(batch, fail_silently=False)
                sent_count += len(batch)
            except Exception as e:
                logger.error(f"Error sending weekly digest batch: {e}")

        logger.info(f"Weekly digest sent to {sent_count} subscribers")

    except Exception as exc:
        logger.error(f"Error sending weekly digest: {exc}")
        self.retry(countdown=300, exc=exc)


@shared_task(bind=True, max_retries=3)
def moderate_content_automatically(self):
    """Automatically moderate content based on rules."""
    try:
        # Auto-approve posts from verified authors
        verified_users = User.objects.filter(
            userprofile__is_verified=True, is_staff=False
        )

        pending_posts = BlogPost.objects.filter(
            status=BlogPost.PostStatus.UNDER_REVIEW, author__in=verified_users
        )

        auto_approved = 0
        for post in pending_posts:
            post.status = BlogPost.PostStatus.PUBLISHED
            if not post.published_at:
                post.published_at = timezone.now()
            post.save()
            auto_approved += 1

            # Log moderation action
            BlogModerationLog.objects.create(
                moderator=None,  # System action
                action_type=BlogModerationLog.ActionType.APPROVE,
                content_object=post,
                description="Auto-approved: verified author",
            )

        # Auto-approve comments from verified users
        pending_comments = BlogComment.objects.filter(
            status=BlogComment.CommentStatus.PENDING, author__in=verified_users
        )

        auto_approved_comments = 0
        for comment in pending_comments:
            comment.status = BlogComment.CommentStatus.APPROVED
            comment.save()
            auto_approved_comments += 1

        logger.info(
            f"Auto-approved {auto_approved} posts and {auto_approved_comments} comments"
        )

    except Exception as exc:
        logger.error(f"Error in automatic moderation: {exc}")
        self.retry(countdown=300, exc=exc)


@shared_task(bind=True, max_retries=3)
def backup_blog_data(self):
    """Create backup of important blog data."""
    try:
        import json

        from django.core import serializers

        # Backup posts
        posts = (
            BlogPost.objects.filter(status=BlogPost.PostStatus.PUBLISHED)
            .select_related("author")
            .prefetch_related("categories", "tags")
        )

        {
            "timestamp": timezone.now().isoformat(),
            "posts_count": posts.count(),
            "posts": json.loads(serializers.serialize("json", posts)),
        }

        # Here you would save to cloud storage (S3, etc.)
        # backup_filename = f"blog_backup_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json"
        # upload_to_s3(backup_filename, json.dumps(backup_data))

        logger.info(f"Created backup with {posts.count()} posts")

    except Exception as exc:
        logger.error(f"Error creating blog backup: {exc}")
        self.retry(countdown=600, exc=exc)


# Periodic tasks configuration
@shared_task
def daily_blog_maintenance():
    """Daily maintenance tasks."""
    cleanup_old_analytics.delay()
    update_trending_posts.delay()
    moderate_content_automatically.delay()
    generate_sitemap.delay()


@shared_task
def weekly_blog_maintenance():
    """Weekly maintenance tasks."""
    send_weekly_digest.delay()
    backup_blog_data.delay()


# Helper functions
def get_user_reading_preferences(user: User) -> Dict[str, Any]:
    """Get user's reading preferences for personalized content."""
    try:
        # Get user's most read categories
        top_categories = (
            BlogView.objects.filter(user=user)
            .values("post__categories__name")
            .annotate(count=Count("post__categories"))
            .order_by("-count")[:5]
        )

        # Get user's most used tags
        top_tags = (
            BlogView.objects.filter(user=user)
            .values("post__tags__name")
            .annotate(count=Count("post__tags"))
            .order_by("-count")[:10]
        )

        return {
            "categories": [cat["post__categories__name"] for cat in top_categories],
            "tags": [tag["post__tags__name"] for tag in top_tags],
        }
    except Exception:
        return {"categories": [], "tags": []}


def calculate_content_similarity(post1: BlogPost, post2: BlogPost) -> float:
    """Calculate similarity between two posts for recommendations."""
    try:
        # Simple similarity based on common tags and categories
        common_tags = set(post1.tags.values_list("name", flat=True)) & set(
            post2.tags.values_list("name", flat=True)
        )

        common_categories = set(post1.categories.values_list("name", flat=True)) & set(
            post2.categories.values_list("name", flat=True)
        )

        total_tags = len(
            set(post1.tags.values_list("name", flat=True))
            | set(post2.tags.values_list("name", flat=True))
        )

        total_categories = len(
            set(post1.categories.values_list("name", flat=True))
            | set(post2.categories.values_list("name", flat=True))
        )

        tag_similarity = len(common_tags) / max(total_tags, 1)
        category_similarity = len(common_categories) / max(total_categories, 1)

        return (tag_similarity + category_similarity) / 2
    except Exception:
        return 0.0
