import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models import F
from django.db.models.signals import m2m_changed, post_save, pre_delete
from django.dispatch import receiver

from apps.notifications.models import Notification

from .models import (
    Event,
    EventAnalytics,
    EventBadge,
    EventCategory,
    EventCategoryRelation,
    EventTag,
    EventTagRelation,
    EventView,
    Exhibitor,
    Participant,
    ParticipantBadge,
    Product,
    Session,
    SessionRating,
)

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()


@receiver(post_save, sender=Event)
def event_post_save(sender, instance, created, **kwargs):
    """Handle post-save operations for events."""
    try:
        if created:
            # Create analytics record
            EventAnalytics.objects.get_or_create(event=instance)

            # Create default categories if none exist
            if not EventCategoryRelation.objects.filter(event=instance).exists():
                default_category, _ = EventCategory.objects.get_or_create(
                    name="General", defaults={"description": "General events"}
                )
                EventCategoryRelation.objects.create(
                    event=instance, category=default_category, is_primary=True
                )

            # Send notifications to organizer's followers
            if hasattr(instance.organizer, "followers"):
                followers = instance.organizer.followers.all()[
                    :100
                ]  # Limit to prevent spam
                for follower in followers:
                    Notification.objects.create(
                        recipient=follower.follower,
                        notification_type="event_created",
                        title=f"New event: {instance.name}",
                        message=f"{instance.organizer.get_full_name()} created a new event",
                        data={
                            "event_id": str(instance.id),
                            "event_name": instance.name,
                            "organizer_id": str(instance.organizer.id),
                        },
                    )

        # Update analytics when event is updated
        if hasattr(instance, "analytics"):
            instance.analytics.recalculate()

        # Send real-time updates
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"event_{instance.id}",
                {
                    "type": "event_update",
                    "data": {
                        "event_id": str(instance.id),
                        "status": instance.status,
                        "registration_count": instance.registration_count,
                        "is_live": instance.is_live,
                    },
                },
            )

    except Exception as e:
        logger.error(f"Error in event_post_save signal: {e}", exc_info=True)


@receiver(post_save, sender=Session)
def session_post_save(sender, instance, created, **kwargs):
    """Handle post-save operations for sessions."""
    try:
        # Update event session count
        instance.event.session_count = instance.event.sessions.count()
        instance.event.save(update_fields=["session_count"])

        # Send real-time updates for session changes
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"event_{instance.event.id}",
                {
                    "type": "session_update",
                    "data": {
                        "session_id": str(instance.id),
                        "title": instance.title,
                        "status": instance.status,
                        "start_time": instance.start_time.isoformat(),
                        "is_live": instance.is_live,
                        "attendee_count": instance.attendee_count,
                    },
                },
            )

        # Notify participants about session updates if not created
        if not created and instance.status == Session.SessionStatus.LIVE:
            participants = Participant.objects.filter(
                event=instance.event,
                registration_status=Participant.RegistrationStatus.CONFIRMED,
            ).select_related("user")

            for participant in participants[:50]:  # Limit notifications
                Notification.objects.create(
                    recipient=participant.user,
                    notification_type="session_started",
                    title=f"Session started: {instance.title}",
                    message=f"The session '{instance.title}' has started",
                    data={
                        "session_id": str(instance.id),
                        "event_id": str(instance.event.id),
                        "session_title": instance.title,
                    },
                )

    except Exception as e:
        logger.error(f"Error in session_post_save signal: {e}", exc_info=True)


@receiver(post_save, sender=Participant)
def participant_post_save(sender, instance, created, **kwargs):
    """Handle post-save operations for participants."""
    try:
        with transaction.atomic():
            if created:
                # Update event registration count
                if (
                    instance.registration_status
                    == Participant.RegistrationStatus.CONFIRMED
                ):
                    Event.objects.filter(id=instance.event.id).update(
                        registration_count=F("registration_count") + 1
                    )

                # Send welcome notification
                Notification.objects.create(
                    recipient=instance.user,
                    notification_type="event_registration",
                    title=f"Welcome to {instance.event.name}",
                    message=f"You have successfully registered for {instance.event.name}",
                    data={
                        "event_id": str(instance.event.id),
                        "participant_id": str(instance.id),
                    },
                )

                # Award registration badge if exists
                try:
                    registration_badge = EventBadge.objects.get(name="Early Bird")
                    ParticipantBadge.objects.get_or_create(
                        participant=instance,
                        badge=registration_badge,
                        defaults={"reason": "Registered for event"},
                    )
                except EventBadge.DoesNotExist:
                    pass

            # Check for level up
            old_instance = None
            if not created:
                old_instance = Participant.objects.get(id=instance.id)

            if old_instance and old_instance.points != instance.points:
                check_level_up(instance)

            # Send real-time updates
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"event_{instance.event.id}",
                    {
                        "type": "attendance_update",
                        "data": {
                            "participant_id": str(instance.id),
                            "user_id": str(instance.user.id),
                            "registration_status": instance.registration_status,
                            "attendance_status": instance.attendance_status,
                            "points": instance.points,
                        },
                    },
                )

    except Exception as e:
        logger.error(f"Error in participant_post_save signal: {e}", exc_info=True)


@receiver(pre_delete, sender=Participant)
def participant_pre_delete(sender, instance, **kwargs):
    """Handle pre-delete operations for participants."""
    try:
        # Update event registration count if confirmed
        if instance.registration_status == Participant.RegistrationStatus.CONFIRMED:
            Event.objects.filter(id=instance.event.id).update(
                registration_count=F("registration_count") - 1
            )

    except Exception as e:
        logger.error(f"Error in participant_pre_delete signal: {e}", exc_info=True)


@receiver(post_save, sender=SessionRating)
def session_rating_post_save(sender, instance, created, **kwargs):
    """Handle post-save operations for session ratings."""
    try:
        # Update session average rating
        session = instance.session
        ratings = session.ratings.all()
        avg_rating = sum(r.rating for r in ratings) / len(ratings) if ratings else 0

        Session.objects.filter(id=session.id).update(
            rating_avg=avg_rating, rating_count=len(ratings)
        )

        # Award badges for rating activities
        if created:
            participant = instance.participant
            rating_count = participant.session_ratings.count()

            # Award reviewer badges
            if rating_count == 1:
                try:
                    reviewer_badge = EventBadge.objects.get(name="First Reviewer")
                    ParticipantBadge.objects.get_or_create(
                        participant=participant,
                        badge=reviewer_badge,
                        defaults={"reason": "First session review"},
                    )
                except EventBadge.DoesNotExist:
                    pass
            elif rating_count == 5:
                try:
                    reviewer_badge = EventBadge.objects.get(name="Active Reviewer")
                    ParticipantBadge.objects.get_or_create(
                        participant=participant,
                        badge=reviewer_badge,
                        defaults={"reason": "Reviewed 5 sessions"},
                    )
                except EventBadge.DoesNotExist:
                    pass

            # Add points for rating
            participant.add_points(2, f"Rated session: {session.title}")

    except Exception as e:
        logger.error(f"Error in session_rating_post_save signal: {e}", exc_info=True)


@receiver(m2m_changed, sender=Participant.sessions_attended.through)
def participant_sessions_changed(sender, instance, action, pk_set, **kwargs):
    """Handle changes to participant's attended sessions."""
    try:
        if action == "post_add" and pk_set:
            # Award attendance badges
            attended_count = instance.sessions_attended.count()

            if attended_count == 1:
                try:
                    badge = EventBadge.objects.get(name="First Session")
                    ParticipantBadge.objects.get_or_create(
                        participant=instance,
                        badge=badge,
                        defaults={"reason": "Attended first session"},
                    )
                except EventBadge.DoesNotExist:
                    pass
            elif attended_count == 5:
                try:
                    badge = EventBadge.objects.get(name="Active Attendee")
                    ParticipantBadge.objects.get_or_create(
                        participant=instance,
                        badge=badge,
                        defaults={"reason": "Attended 5 sessions"},
                    )
                except EventBadge.DoesNotExist:
                    pass

            # Update session attendee counts
            for session_id in pk_set:
                Session.objects.filter(id=session_id).update(
                    attendee_count=F("attendee_count") + 1
                )

    except Exception as e:
        logger.error(
            f"Error in participant_sessions_changed signal: {e}", exc_info=True
        )


@receiver(post_save, sender=EventTagRelation)
def event_tag_relation_post_save(sender, instance, created, **kwargs):
    """Handle post-save operations for event tag relations."""
    try:
        if created:
            # Update tag usage count
            EventTag.objects.filter(id=instance.tag.id).update(
                usage_count=F("usage_count") + 1
            )

    except Exception as e:
        logger.error(
            f"Error in event_tag_relation_post_save signal: {e}", exc_info=True
        )


@receiver(pre_delete, sender=EventTagRelation)
def event_tag_relation_pre_delete(sender, instance, **kwargs):
    """Handle pre-delete operations for event tag relations."""
    try:
        # Update tag usage count
        EventTag.objects.filter(id=instance.tag.id).update(
            usage_count=F("usage_count") - 1
        )

    except Exception as e:
        logger.error(
            f"Error in event_tag_relation_pre_delete signal: {e}", exc_info=True
        )


@receiver(post_save, sender=Exhibitor)
def exhibitor_post_save(sender, instance, created, **kwargs):
    """Handle post-save operations for exhibitors."""
    try:
        # Update event exhibitor count
        instance.event.exhibitor_count = instance.event.exhibitors.filter(
            status=Exhibitor.ExhibitorStatus.APPROVED
        ).count()
        instance.event.save(update_fields=["exhibitor_count"])

        # Send approval notification
        if not created and instance.status == Exhibitor.ExhibitorStatus.APPROVED:
            if instance.primary_contact:
                Notification.objects.create(
                    recipient=instance.primary_contact,
                    notification_type="exhibitor_approved",
                    title="Exhibitor application approved",
                    message=f"Your exhibitor application for {instance.event.name} has been approved",
                    data={
                        "event_id": str(instance.event.id),
                        "exhibitor_id": str(instance.id),
                    },
                )

    except Exception as e:
        logger.error(f"Error in exhibitor_post_save signal: {e}", exc_info=True)


@receiver(post_save, sender=Product)
def product_post_save(sender, instance, created, **kwargs):
    """Handle post-save operations for products."""
    try:
        if created:
            # Update event product count
            instance.event.product_count = instance.event.products.count()
            instance.event.save(update_fields=["product_count"])

    except Exception as e:
        logger.error(f"Error in product_post_save signal: {e}", exc_info=True)


@receiver(post_save, sender=EventView)
def event_view_post_save(sender, instance, created, **kwargs):
    """Handle post-save operations for event views."""
    try:
        if created:
            # Update event view count (done in bulk to avoid race conditions)
            Event.objects.filter(id=instance.event.id).update(
                view_count=F("view_count") + 1
            )

    except Exception as e:
        logger.error(f"Error in event_view_post_save signal: {e}", exc_info=True)


def check_level_up(participant):
    """Check if participant should level up and award badges."""
    try:
        # Simple level calculation (100 points per level)
        new_level = min(10, max(1, participant.points // 100 + 1))

        if new_level > participant.level:
            participant.level = new_level
            participant.save(update_fields=["level"])

            # Award level badges
            try:
                level_badge = EventBadge.objects.get(name=f"Level {new_level}")
                ParticipantBadge.objects.get_or_create(
                    participant=participant,
                    badge=level_badge,
                    defaults={"reason": f"Reached level {new_level}"},
                )
            except EventBadge.DoesNotExist:
                pass

            # Send level up notification
            Notification.objects.create(
                recipient=participant.user,
                notification_type="level_up",
                title=f"Level Up! You are now level {new_level}",
                message=f"Congratulations! You've reached level {new_level} in {participant.event.name}",
                data={
                    "event_id": str(participant.event.id),
                    "new_level": new_level,
                    "points": participant.points,
                },
            )

            # Send real-time notification
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"event_{participant.event.id}",
                    {
                        "type": "notification",
                        "data": {
                            "user_id": str(participant.user.id),
                            "type": "level_up",
                            "level": new_level,
                            "points": participant.points,
                        },
                    },
                )

    except Exception as e:
        logger.error(f"Error in check_level_up: {e}", exc_info=True)


def check_networking_badges(participant):
    """Check and award networking-related badges."""
    try:
        connection_count = participant.connections.count()

        if connection_count == 1:
            try:
                badge = EventBadge.objects.get(name="First Connection")
                ParticipantBadge.objects.get_or_create(
                    participant=participant,
                    badge=badge,
                    defaults={"reason": "Made first connection"},
                )
            except EventBadge.DoesNotExist:
                pass
        elif connection_count == 10:
            try:
                badge = EventBadge.objects.get(name="Super Networker")
                ParticipantBadge.objects.get_or_create(
                    participant=participant,
                    badge=badge,
                    defaults={"reason": "Made 10 connections"},
                )
            except EventBadge.DoesNotExist:
                pass

    except Exception as e:
        logger.error(f"Error in check_networking_badges: {e}", exc_info=True)


def update_trending_tags():
    """Update trending status for tags based on recent usage."""
    try:
        # Get tags used in events created in the last 7 days
        from datetime import timedelta

        from django.utils import timezone

        week_ago = timezone.now() - timedelta(days=7)

        recent_tag_usage = (
            EventTagRelation.objects.filter(event__created_at__gte=week_ago)
            .values("tag")
            .annotate(recent_count=models.Count("tag"))
            .order_by("-recent_count")[:10]
        )

        # Reset all trending status
        EventTag.objects.update(is_trending=False)

        # Set trending for top tags
        trending_tag_ids = [item["tag"] for item in recent_tag_usage]
        EventTag.objects.filter(id__in=trending_tag_ids).update(is_trending=True)

    except Exception as e:
        logger.error(f"Error updating trending tags: {e}", exc_info=True)


def update_trending_events():
    """Update trending status for events based on engagement."""
    try:
        from datetime import timedelta

        from django.utils import timezone

        # Calculate trending score based on recent activity
        week_ago = timezone.now() - timedelta(days=7)

        # Reset all trending status
        Event.objects.update(is_trending=False)

        # Get events with high recent engagement
        trending_events = (
            Event.objects.filter(created_at__gte=week_ago)
            .annotate(
                engagement_score=models.F("view_count")
                + models.F("registration_count") * 2
            )
            .order_by("-engagement_score")[:20]
        )

        for event in trending_events:
            event.is_trending = True
            event.save(update_fields=["is_trending"])

    except Exception as e:
        logger.error(f"Error updating trending events: {e}", exc_info=True)


# Periodic tasks (to be called by Celery or cron)
def daily_maintenance():
    """Daily maintenance tasks."""
    try:
        update_trending_tags()
        update_trending_events()

        # Recalculate analytics for active events
        active_events = Event.objects.filter(
            status__in=[Event.EventStatus.LIVE, Event.EventStatus.SCHEDULED]
        )

        for event in active_events:
            if hasattr(event, "analytics"):
                event.analytics.recalculate()

    except Exception as e:
        logger.error(f"Error in daily_maintenance: {e}", exc_info=True)
