import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import (
    Achievement,
    ActivityLog,
    Certification,
    Connection,
    Education,
    Experience,
    Follow,
    Language,
    Message,
    NetworkMembership,
    Notification,
    ProfileStats,
    ProfileView,
    Project,
    Publication,
    Recommendation,
    Resume,
    Skill,
    SkillEndorsement,
    Task,
    TaskComment,
    UserFile,
    UserProfile,
    Volunteer,
)

User = get_user_model()
logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create user profile and stats when a new user is created."""
    if created:
        try:
            # Create user profile
            profile, profile_created = UserProfile.objects.get_or_create(
                user=instance,
                defaults={
                    "display_name": "",
                    "website": "",
                    "profile_visibility": UserProfile.ProfileVisibility.CONNECTIONS_ONLY,
                },
            )

            # Create profile stats
            stats, stats_created = ProfileStats.objects.get_or_create(
                user=instance,
                defaults={
                    "profile_views": 0,
                    "connections_count": 0,
                    "endorsements_count": 0,
                    "project_views": 0,
                    "search_appearances": 0,
                },
            )

            # Log activity only if profile was actually created
            if profile_created:
                ActivityLog.objects.create(
                    user=instance,
                    activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
                    description="Profile created",
                )

            logger.info(
                f"Profile for user {instance.username}: profile_created={profile_created}, stats_created={stats_created}"
            )
        except Exception as e:
            logger.error(f"Error creating user profile: {str(e)}", exc_info=True)


@receiver(post_save, sender=UserProfile)
def update_profile_completeness(sender, instance, **kwargs):
    """Update profile completeness score when profile is updated."""
    try:
        completeness = 0
        total_fields = 8  # Total number of profile fields to check

        # Check profile fields
        if instance.user.bio:
            completeness += 1
        if instance.user.location:
            completeness += 1
        if instance.user.current_position:
            completeness += 1
        if instance.user.current_company:
            completeness += 1
        if instance.website:
            completeness += 1
        if instance.user.phone_number:
            completeness += 1
        if instance.user.profile_picture:
            completeness += 1
        if instance.cover_image:
            completeness += 1

        # Calculate percentage
        completeness_percentage = int((completeness / total_fields) * 100)

        # Update profile stats
        stats, created = ProfileStats.objects.get_or_create(user=instance.user)
        # Only update if ProfileStats has profile_completeness field
        if hasattr(stats, "profile_completeness"):
            stats.profile_completeness = completeness_percentage
            stats.save(update_fields=["profile_completeness"])

        logger.debug(
            f"Updated profile completeness for {instance.user.username}: {completeness_percentage}%"
        )
    except Exception as e:
        logger.error(f"Error updating profile completeness: {str(e)}", exc_info=True)


@receiver(post_save, sender=Connection)
def handle_connection_creation(sender, instance, created, **kwargs):
    """Handle connection creation and updates."""
    if created:
        try:
            # Update connection counts for both users
            for user in [instance.from_user, instance.to_user]:
                stats, created = ProfileStats.objects.get_or_create(user=user)
                stats.connections_count = (
                    Connection.objects.filter(
                        from_user=user, status=Connection.ConnectionStatus.ACCEPTED
                    ).count()
                    + Connection.objects.filter(
                        to_user=user, status=Connection.ConnectionStatus.ACCEPTED
                    ).count()
                )
                stats.save(update_fields=["connections_count"])

            # Create notification for connection request
            if instance.status == Connection.ConnectionStatus.PENDING:
                Notification.objects.create(
                    recipient=instance.to_user,
                    sender=instance.from_user,
                    notification_type=Notification.NotificationType.CONNECTION_REQUEST,
                    title=f"{instance.from_user.get_full_name()} sent you a connection request",
                    message=f"{instance.from_user.get_full_name()} wants to connect with you.",
                    data={"connection_id": str(instance.id)},
                )

            # Create notification for accepted connection
            elif instance.status == Connection.ConnectionStatus.ACCEPTED:
                Notification.objects.create(
                    recipient=instance.from_user,
                    sender=instance.to_user,
                    notification_type=Notification.NotificationType.CONNECTION_ACCEPTED,
                    title=f"{instance.to_user.get_full_name()} accepted your connection request",
                    message=f"You are now connected with {instance.to_user.get_full_name()}.",
                    data={"connection_id": str(instance.id)},
                )

        except Exception as e:
            logger.error(f"Error handling connection creation: {str(e)}", exc_info=True)


@receiver(post_save, sender=Follow)
def handle_follow_creation(sender, instance, created, **kwargs):
    """Handle follow relationships."""
    if created:
        try:
            # Update follower/following counts
            follower_stats, created = ProfileStats.objects.get_or_create(
                user=instance.follower
            )
            following_stats, created = ProfileStats.objects.get_or_create(
                user=instance.following
            )

            # Since ProfileStats doesn't have following_count/followers_count fields,
            # we'll just update the last_updated timestamp
            follower_stats.save()
            following_stats.save()

            # Create notification
            Notification.objects.create(
                recipient=instance.following,
                sender=instance.follower,
                notification_type=Notification.NotificationType.CONNECTION_REQUEST,  # Using closest available type
                title=f"{instance.follower.get_full_name()} started following you",
                message=f"{instance.follower.get_full_name()} started following you.",
                data={"follow_id": str(instance.id)},
            )

        except Exception as e:
            logger.error(f"Error handling follow creation: {str(e)}", exc_info=True)


@receiver(post_delete, sender=Follow)
def handle_follow_deletion(sender, instance, **kwargs):
    """Handle follow relationship deletion."""
    try:
        # Update follower/following counts
        follower_stats, created = ProfileStats.objects.get_or_create(
            user=instance.follower
        )
        following_stats, created = ProfileStats.objects.get_or_create(
            user=instance.following
        )

        # Update following count for follower
        # Update last_updated timestamp
        follower_stats.save()
        following_stats.save()

    except Exception as e:
        logger.error(f"Error handling follow deletion: {str(e)}", exc_info=True)


@receiver(post_save, sender=SkillEndorsement)
def handle_skill_endorsement(sender, instance, created, **kwargs):
    """Handle skill endorsement creation."""
    if created:
        try:
            # Update endorsement count for the skill owner
            skill_owner = instance.skill.user
            stats, created = ProfileStats.objects.get_or_create(user=skill_owner)
            stats.endorsements_count = SkillEndorsement.objects.filter(
                skill__user=skill_owner
            ).count()
            stats.save(update_fields=["endorsements_count"])

            # Create notification
            Notification.objects.create(
                recipient=skill_owner,
                sender=instance.endorser,
                notification_type=Notification.NotificationType.SKILL_ENDORSEMENT,
                title=f"{instance.endorser.get_full_name()} endorsed your {instance.skill.name} skill",
                message=f"{instance.endorser.get_full_name()} endorsed your {instance.skill.name} skill.",
                data={
                    "skill_id": str(instance.skill.id),
                    "endorsement_id": str(instance.id),
                },
            )

        except Exception as e:
            logger.error(f"Error handling skill endorsement: {str(e)}", exc_info=True)


@receiver(post_delete, sender=SkillEndorsement)
def handle_skill_endorsement_deletion(sender, instance, **kwargs):
    """Handle skill endorsement deletion."""
    try:
        # Update endorsement count for the skill owner
        skill_owner = instance.skill.user
        stats, created = ProfileStats.objects.get_or_create(user=skill_owner)
        stats.endorsements_count = SkillEndorsement.objects.filter(
            skill__user=skill_owner
        ).count()
        stats.save(update_fields=["endorsements_count"])

    except Exception as e:
        logger.error(
            f"Error handling skill endorsement deletion: {str(e)}", exc_info=True
        )


@receiver(post_save, sender=ProfileView)
def handle_profile_view(sender, instance, created, **kwargs):
    """Handle profile view tracking."""
    if created:
        try:
            # Update profile view count
            stats, created = ProfileStats.objects.get_or_create(
                user=instance.profile_owner
            )
            stats.profile_views = ProfileView.objects.filter(
                profile_owner=instance.profile_owner
            ).count()
            stats.save(update_fields=["profile_views"])

            # Update last activity for viewed user
            instance.profile_owner.update_last_activity()

        except Exception as e:
            logger.error(f"Error handling profile view: {str(e)}", exc_info=True)


@receiver(post_save, sender=Recommendation)
def handle_recommendation(sender, instance, created, **kwargs):
    """Handle recommendation creation and status changes."""
    try:
        if created:
            # Create notification for new recommendation
            Notification.objects.create(
                recipient=instance.recommendee,
                sender=instance.recommender,
                notification_type=Notification.NotificationType.RECOMMENDATION_RECEIVED,
                title=f"{instance.recommender.get_full_name()} wrote you a recommendation",
                message=f"{instance.recommender.get_full_name()} wrote you a {instance.get_relationship_type_display().lower()} recommendation.",
                data={"recommendation_id": str(instance.id)},
            )

            # Log the recommendation activity
            ActivityLog.objects.create(
                user=instance.recommender,
                activity_type=ActivityLog.ActivityType.RECOMMENDATION_GIVEN,
                description=f"Gave a recommendation to {instance.recommendee.get_full_name()}",
                metadata={"recommendation_id": str(instance.id)},
            )

    except Exception as e:
        logger.error(f"Error handling recommendation: {str(e)}", exc_info=True)


@receiver(post_save, sender=Task)
def handle_task_creation(sender, instance, created, **kwargs):
    """Handle task creation and assignment."""
    if created and instance.assignee:
        try:
            # Create notification for task assignment
            Notification.objects.create(
                recipient=instance.assignee,
                sender=instance.created_by,
                notification_type=Notification.NotificationType.TASK_ASSIGNED,
                title=f"New task assigned: {instance.title}",
                message=f"{instance.created_by.get_full_name()} assigned you a new task: {instance.title}",
                data={
                    "task_id": str(instance.id),
                    "priority": instance.priority,
                    "due_date": (
                        instance.due_date.isoformat() if instance.due_date else None
                    ),
                },
            )

        except Exception as e:
            logger.error(f"Error handling task creation: {str(e)}", exc_info=True)


@receiver(post_save, sender=Message)
def handle_message_creation(sender, instance, created, **kwargs):
    """Handle message creation and notifications."""
    if created:
        try:
            # Create notification for new message
            Notification.objects.create(
                recipient=instance.recipient,
                sender=instance.sender,
                notification_type=Notification.NotificationType.MESSAGE,
                title=f"New message from {instance.sender.get_full_name()}",
                message=(
                    instance.content[:100] + "..."
                    if len(instance.content) > 100
                    else instance.content
                ),
                data={"message_id": str(instance.id)},
            )

            # Update last activity for both users
            instance.sender.update_last_activity()
            instance.recipient.update_last_activity()

        except Exception as e:
            logger.error(f"Error handling message creation: {str(e)}", exc_info=True)


@receiver(post_save, sender=Experience)
@receiver(post_save, sender=Education)
@receiver(post_save, sender=Skill)
@receiver(post_save, sender=Project)
@receiver(post_save, sender=Achievement)
@receiver(post_save, sender=Publication)
@receiver(post_save, sender=Volunteer)
@receiver(post_save, sender=Language)
@receiver(post_save, sender=Certification)
def update_profile_on_content_change(sender, instance, created, **kwargs):
    """Update profile completeness when profile content changes."""
    try:
        if hasattr(instance, "user"):
            # Trigger profile completeness recalculation
            profile = instance.user.profile
            profile.save()  # This will trigger the UserProfile signal

    except Exception as e:
        logger.error(
            f"Error updating profile on content change: {str(e)}", exc_info=True
        )


@receiver(post_save, sender=UserFile)
def handle_file_upload(sender, instance, created, **kwargs):
    """Handle file upload and virus scanning."""
    if created:
        try:
            # Log file upload activity
            ActivityLog.objects.create(
                user=instance.user,
                activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
                description=f"Uploaded file: {instance.name}",
                metadata={
                    "file_type": instance.file_type,
                    "file_size": instance.size,
                    "file_name": instance.name,
                },
            )

            # TODO: Add virus scanning logic here
            # You can integrate with services like ClamAV or cloud-based scanners

        except Exception as e:
            logger.error(f"Error handling file upload: {str(e)}", exc_info=True)


@receiver(pre_save, sender=User)
def handle_user_status_change(sender, instance, **kwargs):
    """Handle user status changes."""
    try:
        if instance.pk:  # Existing user
            old_user = User.objects.get(pk=instance.pk)

            # Check if status changed
            if old_user.status != instance.status:
                ActivityLog.objects.create(
                    user=instance,
                    activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
                    description=f"Status changed from {old_user.get_status_display()} to {instance.get_status_display()}",
                )

                # If user became inactive, handle cleanup
                if instance.status == User.UserStatus.INACTIVE:
                    # Set all tasks as inactive or reassign them
                    Task.objects.filter(
                        assignee=instance,
                        status__in=[Task.TaskStatus.TODO, Task.TaskStatus.IN_PROGRESS],
                    ).update(status=Task.TaskStatus.CANCELLED)

    except Exception as e:
        logger.error(f"Error handling user status change: {str(e)}", exc_info=True)


@receiver(post_save, sender=TaskComment)
def handle_task_comment(sender, instance, created, **kwargs):
    """Handle task comment notifications."""
    if created:
        try:
            task = instance.task

            # Notify task assignee if comment is not from them
            if task.assignee and task.assignee != instance.author:
                Notification.objects.create(
                    recipient=task.assignee,
                    sender=instance.author,
                    notification_type=Notification.NotificationType.TASK_ASSIGNED,  # Using closest available
                    title=f"New comment on task: {task.title}",
                    message=f"{instance.author.get_full_name()} commented on task: {task.title}",
                    data={
                        "task_id": str(task.id),
                        "comment_id": str(instance.id),
                    },
                )

            # Notify task creator if comment is not from them
            if (
                task.created_by
                and task.created_by != instance.author
                and task.created_by != task.assignee
            ):
                Notification.objects.create(
                    recipient=task.created_by,
                    sender=instance.author,
                    notification_type=Notification.NotificationType.TASK_ASSIGNED,  # Using closest available
                    title=f"New comment on your task: {task.title}",
                    message=f"{instance.author.get_full_name()} commented on your task: {task.title}",
                    data={
                        "task_id": str(task.id),
                        "comment_id": str(instance.id),
                    },
                )

        except Exception as e:
            logger.error(f"Error handling task comment: {str(e)}", exc_info=True)


@receiver(post_save, sender=NetworkMembership)
def handle_network_membership(sender, instance, created, **kwargs):
    """Handle network membership changes."""
    if created:
        try:
            # Create welcome notification for approved memberships
            if instance.status == NetworkMembership.MembershipStatus.APPROVED:
                Notification.objects.create(
                    recipient=instance.user,
                    notification_type=Notification.NotificationType.NETWORK_INVITATION,
                    title=f"Welcome to {instance.network.name}",
                    message=f"You have been approved to join {instance.network.name} network.",
                    data={"network_id": str(instance.network.id)},
                )

        except Exception as e:
            logger.error(f"Error handling network membership: {str(e)}", exc_info=True)


def cleanup_old_notifications():
    """
    Cleanup function to remove old notifications.
    This should be called periodically (e.g., via celery task).
    """
    try:
        # Delete read notifications older than 30 days
        thirty_days_ago = timezone.now() - timedelta(days=30)
        old_notifications = Notification.objects.filter(
            is_read=True, created_at__lt=thirty_days_ago
        )
        deleted_count = old_notifications.count()
        old_notifications.delete()

        logger.info(f"Cleaned up {deleted_count} old notifications")

    except Exception as e:
        logger.error(f"Error cleaning up notifications: {str(e)}", exc_info=True)


def cleanup_old_activity_logs():
    """
    Cleanup function to remove old activity logs.
    This should be called periodically (e.g., via celery task).
    """
    try:
        # Delete activity logs older than 90 days
        ninety_days_ago = timezone.now() - timedelta(days=90)
        old_logs = ActivityLog.objects.filter(created_at__lt=ninety_days_ago)
        deleted_count = old_logs.count()
        old_logs.delete()

        logger.info(f"Cleaned up {deleted_count} old activity logs")

    except Exception as e:
        logger.error(f"Error cleaning up activity logs: {str(e)}", exc_info=True)


def send_skill_endorsement_reminders():
    """
    Send reminders to users to endorse skills of their connections.
    This should be called periodically.
    """
    try:
        # Get users who haven't received endorsements recently
        one_month_ago = timezone.now() - timedelta(days=30)

        users_needing_endorsements = User.objects.filter(
            status=User.UserStatus.ACTIVE,
            skills__endorsements__created_at__lt=one_month_ago,
        ).distinct()

        for user in users_needing_endorsements:
            # Get user's connections
            connections = Connection.objects.filter(
                Q(from_user=user) | Q(to_user=user),
                status=Connection.ConnectionStatus.ACCEPTED,
            )

            for connection in connections:
                other_user = (
                    connection.to_user
                    if connection.from_user == user
                    else connection.from_user
                )

                # Check if they haven't endorsed recently
                recent_endorsements = SkillEndorsement.objects.filter(
                    skill__user=user, endorser=other_user, created_at__gte=one_month_ago
                ).exists()

                if not recent_endorsements:
                    Notification.objects.create(
                        recipient=other_user,
                        notification_type=Notification.NotificationType.SKILL_ENDORSEMENT,
                        title=f"Endorse {user.get_full_name()}'s skills",
                        message=f"Consider endorsing {user.get_full_name()}'s skills to help them grow their professional profile.",
                        data={"user_id": str(user.id)},
                    )

    except Exception as e:
        logger.error(f"Error sending endorsement reminders: {str(e)}", exc_info=True)


def update_user_activity_status():
    """
    Update user online/offline status based on last activity.
    This should be called periodically.
    """
    try:
        # Mark users as offline if they haven't been active for 15 minutes
        fifteen_minutes_ago = timezone.now() - timedelta(minutes=15)

        User.objects.filter(
            last_activity__lt=fifteen_minutes_ago, is_online=True
        ).update(is_online=False)

        # Mark users as online if they've been active within 5 minutes
        five_minutes_ago = timezone.now() - timedelta(minutes=5)

        User.objects.filter(
            last_activity__gte=five_minutes_ago, is_online=False
        ).update(is_online=True)

    except Exception as e:
        logger.error(f"Error updating user activity status: {str(e)}", exc_info=True)


@receiver(post_save, sender=Resume)
def handle_resume_updates(sender, instance, created, **kwargs):
    """Handle resume creation and updates."""
    try:
        if created:
            # If this is the first resume, make it default
            if Resume.objects.filter(user=instance.user).count() == 1:
                instance.is_default = True
                instance.save(update_fields=["is_default"])

        # If setting as default, unset others
        if instance.is_default:
            Resume.objects.filter(user=instance.user).exclude(id=instance.id).update(
                is_default=False
            )

    except Exception as e:
        logger.error(f"Error handling resume updates: {str(e)}", exc_info=True)


def send_connection_suggestions():
    """
    Send connection suggestions to users based on mutual connections,
    same company, education, etc.
    This should be called periodically.
    """
    try:
        active_users = User.objects.filter(status=User.UserStatus.ACTIVE)

        for user in active_users:
            # Get mutual connections
            user_connections = Connection.objects.filter(
                Q(from_user=user) | Q(to_user=user),
                status=Connection.ConnectionStatus.ACCEPTED,
            )

            suggested_users = set()

            # Find users with mutual connections
            for connection in user_connections:
                other_user = (
                    connection.to_user
                    if connection.from_user == user
                    else connection.from_user
                )

                # Get other user's connections
                other_connections = Connection.objects.filter(
                    Q(from_user=other_user) | Q(to_user=other_user),
                    status=Connection.ConnectionStatus.ACCEPTED,
                ).exclude(
                    Q(from_user=user)
                    | Q(to_user=user)  # Exclude existing connections with main user
                )

                for other_conn in other_connections[:3]:  # Limit suggestions
                    suggested_user = (
                        other_conn.to_user
                        if other_conn.from_user == other_user
                        else other_conn.from_user
                    )
                    if suggested_user != user:
                        suggested_users.add(suggested_user)

            # Find users from same company
            if hasattr(user, "userprofile") and user.userprofile.current_position:
                current_experiences = Experience.objects.filter(
                    user=user, is_current=True
                ).values_list("company", flat=True)

                for company in current_experiences:
                    same_company_users = (
                        Experience.objects.filter(company=company, is_current=True)
                        .exclude(user=user)
                        .values_list("user", flat=True)
                    )

                    for user_id in same_company_users[:2]:  # Limit suggestions
                        try:
                            suggested_user = User.objects.get(id=user_id)
                            suggested_users.add(suggested_user)
                        except User.DoesNotExist:
                            continue

            # Send notifications for suggestions (limit to 5 per day)
            existing_suggestions_today = Notification.objects.filter(
                recipient=user,
                notification_type=Notification.NotificationType.CONNECTION_REQUEST,
                created_at__date=timezone.now().date(),
                title__icontains="You might know",
            ).count()

            if existing_suggestions_today < 5:
                for suggested_user in list(suggested_users)[
                    : 5 - existing_suggestions_today
                ]:
                    # Check if already connected or request pending
                    existing_connection = Connection.objects.filter(
                        Q(from_user=user, to_user=suggested_user)
                        | Q(from_user=suggested_user, to_user=user)
                    ).exists()

                    if not existing_connection:
                        Notification.objects.create(
                            recipient=user,
                            notification_type=Notification.NotificationType.CONNECTION_REQUEST,
                            title=f"You might know {suggested_user.get_full_name()}",
                            message=f"Connect with {suggested_user.get_full_name()} to expand your network.",
                            data={"suggested_user_id": str(suggested_user.id)},
                        )

    except Exception as e:
        logger.error(f"Error sending connection suggestions: {str(e)}", exc_info=True)


def send_weekly_digest():
    """
    Send weekly digest of activities to users.
    This should be called weekly.
    """
    try:
        one_week_ago = timezone.now() - timedelta(days=7)
        active_users = User.objects.filter(
            status=User.UserStatus.ACTIVE, last_activity__gte=one_week_ago
        )

        for user in active_users:
            # Get week's statistics
            week_stats = {
                "profile_views": ProfileView.objects.filter(
                    profile_owner=user, created_at__gte=one_week_ago
                ).count(),
                "new_connections": Connection.objects.filter(
                    Q(from_user=user) | Q(to_user=user),
                    status=Connection.ConnectionStatus.ACCEPTED,
                    updated_at__gte=one_week_ago,
                ).count(),
                "endorsements_received": SkillEndorsement.objects.filter(
                    skill__user=user, created_at__gte=one_week_ago
                ).count(),
                "recommendations_received": Recommendation.objects.filter(
                    recommended_user=user,
                    status=Recommendation.RecommendationStatus.APPROVED,
                    updated_at__gte=one_week_ago,
                ).count(),
            }

            # Only send if there's activity to report
            if any(week_stats.values()):
                Notification.objects.create(
                    recipient=user,
                    notification_type=Notification.NotificationType.PROFILE_VIEW,  # Using closest available
                    title="Your weekly profile summary",
                    message=f"This week: {week_stats['profile_views']} profile views, {week_stats['new_connections']} new connections, {week_stats['endorsements_received']} endorsements received.",
                    data=week_stats,
                )

    except Exception as e:
        logger.error(f"Error sending weekly digest: {str(e)}", exc_info=True)


def cleanup_expired_connections():
    """
    Cleanup expired connection requests.
    This should be called daily.
    """
    try:
        # Delete connection requests older than 30 days
        thirty_days_ago = timezone.now() - timedelta(days=30)
        expired_requests = Connection.objects.filter(
            status=Connection.ConnectionStatus.PENDING, created_at__lt=thirty_days_ago
        )

        deleted_count = expired_requests.count()
        expired_requests.delete()

        logger.info(f"Cleaned up {deleted_count} expired connection requests")

    except Exception as e:
        logger.error(f"Error cleaning up expired connections: {str(e)}", exc_info=True)


def update_trending_skills():
    """
    Update trending skills based on recent endorsements and new additions.
    This should be called daily.
    """
    try:
        # Get skills with most endorsements in the last 7 days
        one_week_ago = timezone.now() - timedelta(days=7)

        trending_skills = (
            Skill.objects.filter(endorsements__created_at__gte=one_week_ago)
            .annotate(recent_endorsements=Count("endorsements"))
            .order_by("-recent_endorsements")[:20]
        )

        # Store trending skills in cache or database
        # This could be used for skill suggestions

        logger.info(
            f"Updated trending skills: {[skill.name for skill in trending_skills]}"
        )

    except Exception as e:
        logger.error(f"Error updating trending skills: {str(e)}", exc_info=True)


def send_birthday_notifications():
    """
    Send birthday notifications to connections.
    This should be called daily.
    """
    try:
        from datetime import date

        today = date.today()

        # Find users with birthdays today
        birthday_users = User.objects.filter(
            userprofile__date_of_birth__month=today.month,
            userprofile__date_of_birth__day=today.day,
            status=User.UserStatus.ACTIVE,
        )

        for birthday_user in birthday_users:
            # Get their connections
            connections = Connection.objects.filter(
                Q(from_user=birthday_user) | Q(to_user=birthday_user),
                status=Connection.ConnectionStatus.ACCEPTED,
            )

            for connection in connections:
                other_user = (
                    connection.to_user
                    if connection.from_user == birthday_user
                    else connection.from_user
                )

                # Check if notification already sent today
                existing_notification = Notification.objects.filter(
                    recipient=other_user,
                    notification_type=Notification.NotificationType.PROFILE_VIEW,  # Using closest available
                    title__icontains=f"{birthday_user.get_full_name()}'s birthday",
                    created_at__date=today,
                ).exists()

                if not existing_notification:
                    Notification.objects.create(
                        recipient=other_user,
                        notification_type=Notification.NotificationType.PROFILE_VIEW,  # Using closest available
                        title=f"It's {birthday_user.get_full_name()}'s birthday!",
                        message=f"Wish {birthday_user.get_full_name()} a happy birthday.",
                        data={"birthday_user_id": str(birthday_user.id)},
                    )

        logger.info(f"Sent birthday notifications for {birthday_users.count()} users")

    except Exception as e:
        logger.error(f"Error sending birthday notifications: {str(e)}", exc_info=True)


def send_task_deadline_reminders():
    """
    Send reminders for upcoming task deadlines.
    This should be called daily.
    """
    try:
        # Get tasks due in the next 3 days
        three_days_from_now = timezone.now().date() + timedelta(days=3)
        tomorrow = timezone.now().date() + timedelta(days=1)

        upcoming_tasks = Task.objects.filter(
            due_date__lte=three_days_from_now,
            due_date__gte=tomorrow,
            status__in=[Task.TaskStatus.TODO, Task.TaskStatus.IN_PROGRESS],
        ).select_related("assignee", "created_by")

        for task in upcoming_tasks:
            if task.assignee:
                # Check if reminder already sent today
                existing_reminder = Notification.objects.filter(
                    recipient=task.assignee,
                    notification_type=Notification.NotificationType.TASK_ASSIGNED,
                    title__icontains=f"Task due soon: {task.title}",
                    created_at__date=timezone.now().date(),
                ).exists()

                if not existing_reminder:
                    days_until_due = (task.due_date - timezone.now().date()).days
                    Notification.objects.create(
                        recipient=task.assignee,
                        notification_type=Notification.NotificationType.TASK_ASSIGNED,
                        title=f"Task due soon: {task.title}",
                        message=f"Your task '{task.title}' is due in {days_until_due} days.",
                        data={
                            "task_id": str(task.id),
                            "days_until_due": days_until_due,
                            "priority": task.priority,
                        },
                    )

        logger.info(f"Sent deadline reminders for {upcoming_tasks.count()} tasks")

    except Exception as e:
        logger.error(f"Error sending task deadline reminders: {str(e)}", exc_info=True)


def calculate_profile_engagement_score():
    """
    Calculate engagement score for all users based on activity.
    This should be called weekly.
    """
    try:
        one_week_ago = timezone.now() - timedelta(days=7)

        for user in User.objects.filter(status=User.UserStatus.ACTIVE):
            score = 0

            # Profile views (weight: 1)
            score += ProfileView.objects.filter(
                profile_owner=user, created_at__gte=one_week_ago
            ).count()

            # Endorsements received (weight: 3)
            score += (
                SkillEndorsement.objects.filter(
                    skill__user=user, created_at__gte=one_week_ago
                ).count()
                * 3
            )

            # Recommendations received (weight: 5)
            score += (
                Recommendation.objects.filter(
                    recommended_user=user,
                    status=Recommendation.RecommendationStatus.APPROVED,
                    updated_at__gte=one_week_ago,
                ).count()
                * 5
            )

            # New connections (weight: 4)
            score += (
                Connection.objects.filter(
                    Q(from_user=user) | Q(to_user=user),
                    status=Connection.ConnectionStatus.ACCEPTED,
                    updated_at__gte=one_week_ago,
                ).count()
                * 4
            )

            # Messages sent/received (weight: 2)
            score += (
                Message.objects.filter(
                    Q(sender=user) | Q(recipient=user), created_at__gte=one_week_ago
                ).count()
                * 2
            )

            # Update profile stats
            stats, created = ProfileStats.objects.get_or_create(user=user)
            stats.engagement_score = score
            stats.save(update_fields=["engagement_score"])

        logger.info("Updated engagement scores for all active users")

    except Exception as e:
        logger.error(f"Error calculating engagement scores: {str(e)}", exc_info=True)


def update_skill_trending_scores():
    """
    Update trending scores for skills based on recent activity.
    This should be called daily.
    """
    try:
        one_week_ago = timezone.now() - timedelta(days=7)

        # Get all skills with recent activity
        active_skills = Skill.objects.filter(
            Q(endorsements__created_at__gte=one_week_ago)
            | Q(created_at__gte=one_week_ago)
        ).distinct()

        for skill in active_skills:
            # Calculate trending score
            score = 0

            # Recent endorsements (weight: 3)
            recent_endorsements = SkillEndorsement.objects.filter(
                skill=skill, created_at__gte=one_week_ago
            ).count()
            score += recent_endorsements * 3

            # If skill was recently added (weight: 1)
            if skill.created_at >= one_week_ago:
                score += 1

            # Total endorsements (normalized, weight: 1)
            total_endorsements = skill.endorsements.count()
            score += min(total_endorsements, 10)  # Cap at 10

            # Update skill with trending score (you might want to add this field to the model)
            # skill.trending_score = score
            # skill.save(update_fields=['trending_score'])

        logger.info(f"Updated trending scores for {active_skills.count()} skills")

    except Exception as e:
        logger.error(f"Error updating skill trending scores: {str(e)}", exc_info=True)


def detect_profile_anomalies():
    """
    Detect unusual activity patterns that might indicate suspicious behavior.
    This should be called hourly.
    """
    try:
        one_hour_ago = timezone.now() - timedelta(hours=1)

        # Check for unusual endorsement patterns
        users_with_many_endorsements = (
            User.objects.filter(skills__endorsements__created_at__gte=one_hour_ago)
            .annotate(recent_endorsements=Count("skills__endorsements"))
            .filter(recent_endorsements__gt=10)
        )

        for user in users_with_many_endorsements:
            logger.warning(
                f"User {user.username} received {user.recent_endorsements} endorsements in the last hour"
            )
            # You could send admin notifications or flag accounts here

        # Check for rapid connection requests
        users_with_many_requests = (
            User.objects.filter(connections_sent__created_at__gte=one_hour_ago)
            .annotate(recent_requests=Count("connections_sent"))
            .filter(recent_requests__gt=20)
        )

        for user in users_with_many_requests:
            logger.warning(
                f"User {user.username} sent {user.recent_requests} connection requests in the last hour"
            )
            # You could temporarily limit their connection abilities

    except Exception as e:
        logger.error(f"Error detecting profile anomalies: {str(e)}", exc_info=True)
