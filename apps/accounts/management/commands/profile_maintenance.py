import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from apps.accounts.models import (
    Connection,
    Experience,
    Follow,
    Notification,
    ProfileStats,
    ProfileView,
    Recommendation,
    Resume,
    Skill,
    SkillEndorsement,
    Task,
    UserProfile,
)
from apps.accounts.signals import (
    calculate_profile_engagement_score,
    cleanup_expired_connections,
    cleanup_old_activity_logs,
    cleanup_old_notifications,
    detect_profile_anomalies,
    send_birthday_notifications,
    send_connection_suggestions,
    send_skill_endorsement_reminders,
    send_task_deadline_reminders,
    send_weekly_digest,
    update_skill_trending_scores,
    update_trending_skills,
    update_user_activity_status,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Management command for periodic profile system maintenance.

    This command performs various maintenance tasks including:
    - Cleaning up old data
    - Sending notifications and reminders
    - Updating statistics and scores
    - Detecting anomalies
    """

    help = "Perform periodic maintenance tasks for the profile system"

    def add_arguments(self, parser):
        parser.add_argument(
            "--task",
            type=str,
            choices=[
                "cleanup",
                "notifications",
                "statistics",
                "all",
                "hourly",
                "daily",
                "weekly",
            ],
            default="all",
            help="Specify which maintenance task to run",
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without actually doing it",
        )

        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Enable verbose output",
        )

    def handle(self, *args, **options):
        """Main command handler."""
        self.dry_run = options.get("dry_run", False)
        self.verbose = options.get("verbose", False)
        task = options.get("task", "all")

        if self.verbose:
            self.stdout.write("Starting profile maintenance tasks...")

        try:
            if task == "all":
                self.run_all_tasks()
            elif task == "hourly":
                self.run_hourly_tasks()
            elif task == "daily":
                self.run_daily_tasks()
            elif task == "weekly":
                self.run_weekly_tasks()
            elif task == "cleanup":
                self.run_cleanup_tasks()
            elif task == "notifications":
                self.run_notification_tasks()
            elif task == "statistics":
                self.run_statistics_tasks()

            self.stdout.write(
                self.style.SUCCESS("Profile maintenance completed successfully!")
            )

        except Exception as e:
            logger.error(f"Error during profile maintenance: {str(e)}", exc_info=True)
            self.stdout.write(self.style.ERROR(f"Profile maintenance failed: {str(e)}"))

    def run_all_tasks(self):
        """Run all maintenance tasks."""
        self.run_hourly_tasks()
        self.run_daily_tasks()
        self.run_weekly_tasks()

    def run_hourly_tasks(self):
        """Run tasks that should be executed hourly."""
        if self.verbose:
            self.stdout.write("Running hourly tasks...")

        # Update user activity status
        if not self.dry_run:
            update_user_activity_status()
        self._log_task("Updated user activity status")

        # Detect profile anomalies
        if not self.dry_run:
            detect_profile_anomalies()
        self._log_task("Checked for profile anomalies")

        # Send task deadline reminders for urgent tasks (due in 24 hours)
        if not self.dry_run:
            self._send_urgent_task_reminders()
        self._log_task("Sent urgent task deadline reminders")

    def run_daily_tasks(self):
        """Run tasks that should be executed daily."""
        if self.verbose:
            self.stdout.write("Running daily tasks...")

        # Send birthday notifications
        if not self.dry_run:
            send_birthday_notifications()
        self._log_task("Sent birthday notifications")

        # Send task deadline reminders
        if not self.dry_run:
            send_task_deadline_reminders()
        self._log_task("Sent task deadline reminders")

        # Update trending skills
        if not self.dry_run:
            update_trending_skills()
        self._log_task("Updated trending skills")

        # Update skill trending scores
        if not self.dry_run:
            update_skill_trending_scores()
        self._log_task("Updated skill trending scores")

        # Cleanup expired connections
        if not self.dry_run:
            cleanup_expired_connections()
        self._log_task("Cleaned up expired connections")

        # Cleanup old profile views
        if not self.dry_run:
            self._cleanup_old_profile_views()
        self._log_task("Cleaned up old profile views")

        # Update profile completeness scores
        if not self.dry_run:
            self._update_profile_completeness()
        self._log_task("Updated profile completeness scores")

    def run_weekly_tasks(self):
        """Run tasks that should be executed weekly."""
        if self.verbose:
            self.stdout.write("Running weekly tasks...")

        # Send weekly digest
        if not self.dry_run:
            send_weekly_digest()
        self._log_task("Sent weekly digest")

        # Send skill endorsement reminders
        if not self.dry_run:
            send_skill_endorsement_reminders()
        self._log_task("Sent skill endorsement reminders")

        # Send connection suggestions
        if not self.dry_run:
            send_connection_suggestions()
        self._log_task("Sent connection suggestions")

        # Calculate engagement scores
        if not self.dry_run:
            calculate_profile_engagement_score()
        self._log_task("Calculated engagement scores")

        # Cleanup old data
        if not self.dry_run:
            cleanup_old_notifications()
            cleanup_old_activity_logs()
        self._log_task("Cleaned up old notifications and activity logs")

        # Generate analytics reports
        if not self.dry_run:
            self._generate_weekly_analytics()
        self._log_task("Generated weekly analytics")

    def run_cleanup_tasks(self):
        """Run cleanup tasks only."""
        if self.verbose:
            self.stdout.write("Running cleanup tasks...")

        if not self.dry_run:
            cleanup_old_notifications()
            cleanup_old_activity_logs()
            cleanup_expired_connections()
            self._cleanup_old_profile_views()
            self._cleanup_orphaned_files()
        self._log_task("Completed all cleanup tasks")

    def run_notification_tasks(self):
        """Run notification-related tasks."""
        if self.verbose:
            self.stdout.write("Running notification tasks...")

        if not self.dry_run:
            send_birthday_notifications()
            send_task_deadline_reminders()
            send_skill_endorsement_reminders()
            send_connection_suggestions()
        self._log_task("Completed all notification tasks")

    def run_statistics_tasks(self):
        """Run statistics and analytics tasks."""
        if self.verbose:
            self.stdout.write("Running statistics tasks...")

        if not self.dry_run:
            calculate_profile_engagement_score()
            update_trending_skills()
            update_skill_trending_scores()
            self._update_profile_completeness()
            self._update_all_profile_stats()
        self._log_task("Completed all statistics tasks")

    def _send_urgent_task_reminders(self):
        """Send reminders for tasks due within 24 hours."""
        try:
            tomorrow = timezone.now().date() + timedelta(days=1)
            urgent_tasks = Task.objects.filter(
                due_date__lte=tomorrow,
                due_date__gte=timezone.now().date(),
                status__in=[Task.TaskStatus.TODO, Task.TaskStatus.IN_PROGRESS],
            ).select_related("assigned_to")

            for task in urgent_tasks:
                if task.assigned_to:
                    # Check if urgent reminder already sent today
                    existing_reminder = Notification.objects.filter(
                        recipient=task.assigned_to,
                        notification_type=Notification.NotificationType.TASK_ASSIGNED,
                        title__icontains=f"URGENT: {task.title}",
                        created_at__date=timezone.now().date(),
                    ).exists()

                    if not existing_reminder:
                        hours_until_due = (
                            timezone.combine(task.due_date, timezone.min.time())
                            - timezone.now()
                        ).total_seconds() / 3600

                        Notification.objects.create(
                            recipient=task.assigned_to,
                            notification_type=Notification.NotificationType.TASK_ASSIGNED,
                            title=f"URGENT: {task.title} due soon!",
                            message=f"Your task '{task.title}' is due in {int(hours_until_due)} hours!",
                            data={
                                "task_id": str(task.id),
                                "hours_until_due": int(hours_until_due),
                                "priority": task.priority,
                                "is_urgent": True,
                            },
                        )

            logger.info(f"Sent urgent reminders for {urgent_tasks.count()} tasks")

        except Exception as e:
            logger.error(
                f"Error sending urgent task reminders: {str(e)}", exc_info=True
            )

    def _cleanup_old_profile_views(self):
        """Cleanup profile views older than 6 months."""
        try:
            six_months_ago = timezone.now() - timedelta(days=180)
            old_views = ProfileView.objects.filter(created_at__lt=six_months_ago)
            count = old_views.count()
            old_views.delete()

            logger.info(f"Cleaned up {count} old profile views")

        except Exception as e:
            logger.error(f"Error cleaning up profile views: {str(e)}", exc_info=True)

    def _cleanup_orphaned_files(self):
        """Cleanup orphaned user files."""
        try:
            from apps.accounts.models import UserFile

            orphaned_count = 0

            # Find files in database that don't exist on disk
            for user_file in UserFile.objects.all():
                if user_file.file and not user_file.file.storage.exists(
                    user_file.file.name
                ):
                    user_file.delete()
                    orphaned_count += 1

            logger.info(f"Cleaned up {orphaned_count} orphaned files")

        except Exception as e:
            logger.error(f"Error cleaning up orphaned files: {str(e)}", exc_info=True)

    def _update_profile_completeness(self):
        """Update profile completeness for all users."""
        try:
            updated_count = 0

            for user in User.objects.filter(status=User.UserStatus.ACTIVE):
                try:
                    profile = user.userprofile
                    # Trigger profile completeness recalculation
                    profile.save()
                    updated_count += 1
                except UserProfile.DoesNotExist:
                    # Create profile if it doesn't exist
                    UserProfile.objects.create(user=user)
                    updated_count += 1

            logger.info(f"Updated profile completeness for {updated_count} users")

        except Exception as e:
            logger.error(
                f"Error updating profile completeness: {str(e)}", exc_info=True
            )

    def _update_all_profile_stats(self):
        """Update all profile statistics."""
        try:
            updated_count = 0

            for user in User.objects.filter(status=User.UserStatus.ACTIVE):
                stats, created = ProfileStats.objects.get_or_create(user=user)

                # Update all counts
                stats.profile_views = ProfileView.objects.filter(
                    viewed_user=user
                ).count()

                stats.connections_count = (
                    Connection.objects.filter(
                        from_user=user, status=Connection.ConnectionStatus.ACCEPTED
                    ).count()
                    + Connection.objects.filter(
                        to_user=user, status=Connection.ConnectionStatus.ACCEPTED
                    ).count()
                )

                stats.followers_count = Follow.objects.filter(following=user).count()
                stats.following_count = Follow.objects.filter(follower=user).count()

                stats.endorsements_count = SkillEndorsement.objects.filter(
                    skill__user=user
                ).count()

                stats.recommendations_count = Recommendation.objects.filter(
                    recommended_user=user,
                    status=Recommendation.RecommendationStatus.APPROVED,
                ).count()

                stats.save()
                updated_count += 1

            logger.info(f"Updated profile statistics for {updated_count} users")

        except Exception as e:
            logger.error(f"Error updating profile statistics: {str(e)}", exc_info=True)

    def _generate_weekly_analytics(self):
        """Generate weekly analytics and insights."""
        try:
            one_week_ago = timezone.now() - timedelta(days=7)

            analytics = {
                "new_users": User.objects.filter(date_joined__gte=one_week_ago).count(),
                "new_connections": Connection.objects.filter(
                    status=Connection.ConnectionStatus.ACCEPTED,
                    updated_at__gte=one_week_ago,
                ).count(),
                "new_endorsements": SkillEndorsement.objects.filter(
                    created_at__gte=one_week_ago
                ).count(),
                "new_recommendations": Recommendation.objects.filter(
                    status=Recommendation.RecommendationStatus.APPROVED,
                    created_at__gte=one_week_ago,
                ).count(),
                "active_users": User.objects.filter(
                    last_activity__gte=one_week_ago
                ).count(),
                "top_skills": list(
                    Skill.objects.filter(endorsements__created_at__gte=one_week_ago)
                    .annotate(endorsement_count=Count("endorsements"))
                    .order_by("-endorsement_count")[:10]
                    .values_list("name", flat=True)
                ),
                "top_companies": list(
                    Experience.objects.filter(
                        is_current=True, created_at__gte=one_week_ago
                    )
                    .values("company")
                    .annotate(count=Count("company"))
                    .order_by("-count")[:10]
                    .values_list("company", flat=True)
                ),
            }

            # Store analytics (you might want to create an Analytics model)
            logger.info(f"Weekly analytics generated: {analytics}")

            # You could save this to a model, send to admin users, or export to file
            if self.verbose:
                self.stdout.write(f"Weekly Analytics: {analytics}")

        except Exception as e:
            logger.error(f"Error generating weekly analytics: {str(e)}", exc_info=True)

    def _detect_inactive_users(self):
        """Detect and handle inactive users."""
        try:
            # Users inactive for 6 months
            six_months_ago = timezone.now() - timedelta(days=180)
            inactive_users = User.objects.filter(
                last_activity__lt=six_months_ago,
                status=User.UserStatus.ACTIVE,
            )

            if self.dry_run:
                self.stdout.write(
                    f"Would mark {inactive_users.count()} users as inactive"
                )
            else:
                # Send reactivation email before marking inactive
                for user in inactive_users:
                    # Create notification for reactivation
                    Notification.objects.create(
                        recipient=user,
                        notification_type=Notification.NotificationType.PROFILE_VIEW,
                        title="Your account will be marked as inactive",
                        message="You haven't been active recently. Please log in to keep your account active.",
                        data={"reactivation_required": True},
                    )

                logger.info(
                    f"Sent reactivation notices to {inactive_users.count()} users"
                )

        except Exception as e:
            logger.error(f"Error detecting inactive users: {str(e)}", exc_info=True)

    def _optimize_database(self):
        """Perform database optimization tasks."""
        try:
            # Remove duplicate skill endorsements
            duplicate_endorsements = (
                SkillEndorsement.objects.values("skill", "endorser")
                .annotate(count=Count("id"))
                .filter(count__gt=1)
            )

            removed_duplicates = 0
            for dup in duplicate_endorsements:
                # Keep the latest, remove others
                endorsements = SkillEndorsement.objects.filter(
                    skill_id=dup["skill"], endorser_id=dup["endorser"]
                ).order_by("-created_at")

                if not self.dry_run:
                    endorsements[1:].delete()
                removed_duplicates += dup["count"] - 1

            if self.verbose:
                self.stdout.write(
                    f"Removed {removed_duplicates} duplicate endorsements"
                )

            # Remove duplicate connections
            duplicate_connections = []
            for conn in Connection.objects.all():
                reverse_conn = Connection.objects.filter(
                    from_user=conn.to_user, to_user=conn.from_user
                ).first()

                if reverse_conn and conn.id > reverse_conn.id:
                    duplicate_connections.append(conn)

            if not self.dry_run:
                for conn in duplicate_connections:
                    conn.delete()

            if self.verbose:
                self.stdout.write(
                    f"Removed {len(duplicate_connections)} duplicate connections"
                )

        except Exception as e:
            logger.error(f"Error optimizing database: {str(e)}", exc_info=True)

    def _send_profile_improvement_suggestions(self):
        """Send suggestions to users for improving their profiles."""
        try:
            # Find users with low profile completeness
            low_completeness_users = ProfileStats.objects.filter(
                profile_completeness__lt=60,
                user__status=User.UserStatus.ACTIVE,
                user__last_activity__gte=timezone.now() - timedelta(days=30),
            )

            for stats in low_completeness_users:
                user = stats.user
                suggestions = []

                # Check what's missing
                try:
                    profile = user.userprofile
                    if not profile.bio:
                        suggestions.append("Add a professional bio")
                    if not profile.current_position:
                        suggestions.append("Add your current position")
                    if not profile.profile_picture:
                        suggestions.append("Upload a profile picture")
                    if not Experience.objects.filter(user=user).exists():
                        suggestions.append("Add your work experience")
                    if not Education.objects.filter(user=user).exists():
                        suggestions.append("Add your education background")
                    if not Skill.objects.filter(user=user).exists():
                        suggestions.append("Add your skills")

                    if suggestions and not self.dry_run:
                        Notification.objects.create(
                            recipient=user,
                            notification_type=Notification.NotificationType.PROFILE_VIEW,
                            title="Complete your profile to get discovered",
                            message=f"Your profile is {stats.profile_completeness}% complete. Consider: {', '.join(suggestions[:3])}",
                            data={
                                "suggestions": suggestions,
                                "completeness": stats.profile_completeness,
                            },
                        )

                except UserProfile.DoesNotExist:
                    continue

            logger.info(
                f"Sent profile improvement suggestions to {low_completeness_users.count()} users"
            )

        except Exception as e:
            logger.error(f"Error sending profile suggestions: {str(e)}", exc_info=True)

    def _update_resume_analytics(self):
        """Update resume-related analytics."""
        try:
            # Track resume downloads and views
            # This would require adding tracking fields to the Resume model

            # For now, just count resumes by status
            resume_stats = {
                "total_resumes": Resume.objects.count(),
                "published_resumes": Resume.objects.filter(
                    status=Resume.ResumeStatus.PUBLISHED
                ).count(),
                "draft_resumes": Resume.objects.filter(
                    status=Resume.ResumeStatus.DRAFT
                ).count(),
            }

            logger.info(f"Resume analytics: {resume_stats}")

        except Exception as e:
            logger.error(f"Error updating resume analytics: {str(e)}", exc_info=True)

    def _check_data_integrity(self):
        """Check for data integrity issues."""
        try:
            issues = []

            # Check for users without profiles
            users_without_profiles = User.objects.filter(userprofile__isnull=True)
            if users_without_profiles.exists():
                issues.append(
                    f"{users_without_profiles.count()} users without profiles"
                )

                if not self.dry_run:
                    for user in users_without_profiles:
                        UserProfile.objects.create(user=user)

            # Check for users without stats
            users_without_stats = User.objects.filter(profilestats__isnull=True)
            if users_without_stats.exists():
                issues.append(f"{users_without_stats.count()} users without stats")

                if not self.dry_run:
                    for user in users_without_stats:
                        ProfileStats.objects.create(user=user)

            # Check for invalid connections (user connecting to themselves)
            from django.db import models

            self_connections = Connection.objects.filter(from_user=models.F("to_user"))
            if self_connections.exists():
                issues.append(f"{self_connections.count()} self-connections found")

                if not self.dry_run:
                    self_connections.delete()

            if issues:
                logger.warning(f"Data integrity issues found: {', '.join(issues)}")
            else:
                logger.info("No data integrity issues found")

        except Exception as e:
            logger.error(f"Error checking data integrity: {str(e)}", exc_info=True)

    def _generate_skill_insights(self):
        """Generate insights about skill trends and recommendations."""
        try:
            # Find emerging skills (skills added recently with growing endorsements)
            one_month_ago = timezone.now() - timedelta(days=30)

            emerging_skills = (
                Skill.objects.filter(created_at__gte=one_month_ago)
                .annotate(endorsement_count=Count("endorsements"))
                .filter(endorsement_count__gte=5)
                .order_by("-endorsement_count")[:10]
            )

            # Find skills needing more endorsements
            undervalued_skills = Skill.objects.annotate(
                endorsement_count=Count("endorsements")
            ).filter(endorsement_count=0, created_at__lt=one_month_ago)

            insights = {
                "emerging_skills": list(emerging_skills.values_list("name", flat=True)),
                "undervalued_skills_count": undervalued_skills.count(),
                "total_skills": Skill.objects.count(),
                "total_endorsements": SkillEndorsement.objects.count(),
            }

            logger.info(f"Skill insights generated: {insights}")

        except Exception as e:
            logger.error(f"Error generating skill insights: {str(e)}", exc_info=True)

    def _log_task(self, message):
        """Log task completion."""
        if self.verbose:
            if self.dry_run:
                self.stdout.write(f"[DRY RUN] {message}")
            else:
                self.stdout.write(f"[COMPLETED] {message}")
