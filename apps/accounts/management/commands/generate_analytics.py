import json
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db.models import Avg, Count, Max, Min
from django.utils import timezone

from apps.accounts.models import (
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
    ProfileStats,
    Project,
    Publication,
    Recommendation,
    Resume,
    Skill,
    SkillEndorsement,
    Task,
    UserFile,
    Volunteer,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Management command for generating comprehensive analytics and reports.

    This command generates various analytics reports including:
    - User engagement analytics
    - Skill trends and insights
    - Network growth analysis
    - Profile completeness reports
    - System usage statistics
    """

    help = "Generate comprehensive analytics and reports for the profile system"

    def add_arguments(self, parser):
        parser.add_argument(
            "--report-type",
            type=str,
            choices=[
                "user-engagement",
                "skill-trends",
                "network-growth",
                "profile-completeness",
                "system-usage",
                "admin-summary",
                "all",
            ],
            default="all",
            help="Specify which type of analytics report to generate",
        )

        parser.add_argument(
            "--period",
            type=str,
            choices=["daily", "weekly", "monthly", "quarterly", "yearly"],
            default="weekly",
            help="Time period for the analytics",
        )

        parser.add_argument(
            "--output",
            type=str,
            choices=["console", "json", "email"],
            default="console",
            help="Output format for the report",
        )

        parser.add_argument(
            "--email",
            type=str,
            help="Email address to send the report to (if output is email)",
        )

        parser.add_argument(
            "--save-to-file",
            action="store_true",
            help="Save the report to a file",
        )

    def handle(self, *args, **options):
        """Main command handler."""
        self.report_type = options.get("report_type", "all")
        self.period = options.get("period", "weekly")
        self.output = options.get("output", "console")
        self.email = options.get("email")
        self.save_to_file = options.get("save_to_file", False)

        self.stdout.write("Generating analytics reports...")

        try:
            # Get time period
            self.start_date, self.end_date = self._get_date_range()

            # Generate reports
            reports = {}
            if self.report_type == "all":
                reports.update(self._generate_user_engagement_report())
                reports.update(self._generate_skill_trends_report())
                reports.update(self._generate_network_growth_report())
                reports.update(self._generate_profile_completeness_report())
                reports.update(self._generate_system_usage_report())
                reports.update(self._generate_admin_summary_report())
            elif self.report_type == "user-engagement":
                reports.update(self._generate_user_engagement_report())
            elif self.report_type == "skill-trends":
                reports.update(self._generate_skill_trends_report())
            elif self.report_type == "network-growth":
                reports.update(self._generate_network_growth_report())
            elif self.report_type == "profile-completeness":
                reports.update(self._generate_profile_completeness_report())
            elif self.report_type == "system-usage":
                reports.update(self._generate_system_usage_report())
            elif self.report_type == "admin-summary":
                reports.update(self._generate_admin_summary_report())

            # Output the reports
            self._output_reports(reports)

            self.stdout.write(
                self.style.SUCCESS("Analytics reports generated successfully!")
            )

        except Exception as e:
            logger.error(f"Error generating analytics: {str(e)}", exc_info=True)
            self.stdout.write(
                self.style.ERROR(f"Analytics generation failed: {str(e)}")
            )

    def _get_date_range(self):
        """Get start and end dates based on the period."""
        end_date = timezone.now()

        if self.period == "daily":
            start_date = end_date - timedelta(days=1)
        elif self.period == "weekly":
            start_date = end_date - timedelta(days=7)
        elif self.period == "monthly":
            start_date = end_date - timedelta(days=30)
        elif self.period == "quarterly":
            start_date = end_date - timedelta(days=90)
        elif self.period == "yearly":
            start_date = end_date - timedelta(days=365)
        else:
            start_date = end_date - timedelta(days=7)

        return start_date, end_date

    def _generate_user_engagement_report(self):
        """Generate user engagement analytics."""
        try:
            # Active users in period
            active_users = User.objects.filter(
                last_activity__gte=self.start_date, status=User.UserStatus.ACTIVE
            ).count()

            # New registrations
            new_users = User.objects.filter(date_joined__gte=self.start_date).count()

            # User activity breakdown
            activity_breakdown = {}
            for activity_type in ActivityLog.ActivityType.choices:
                count = ActivityLog.objects.filter(
                    activity_type=activity_type[0], created_at__gte=self.start_date
                ).count()
                activity_breakdown[str(activity_type[1])] = count

            # Top active users
            top_users = (
                ActivityLog.objects.filter(created_at__gte=self.start_date)
                .values("user__username", "user__first_name", "user__last_name")
                .annotate(activity_count=Count("id"))
                .order_by("-activity_count")[:10]
            )

            # Online status distribution
            online_users = User.objects.filter(is_online=True).count()
            total_users = User.objects.filter(status=User.UserStatus.ACTIVE).count()

            # Profile statistics
            profile_stats = ProfileStats.objects.filter(
                user__status=User.UserStatus.ACTIVE
            ).aggregate(
                avg_connections=Avg("connections_count"),
                max_connections=Max("connections_count"),
                min_connections=Min("connections_count"),
            )

            return {
                "user_engagement": {
                    "period": self.period,
                    "start_date": self.start_date.isoformat(),
                    "end_date": self.end_date.isoformat(),
                    "active_users": active_users,
                    "new_users": new_users,
                    "online_users": online_users,
                    "total_users": total_users,
                    "online_percentage": round(
                        (online_users / max(total_users, 1)) * 100, 2
                    ),
                    "activity_breakdown": activity_breakdown,
                    "top_active_users": list(top_users),
                    "profile_statistics": profile_stats,
                }
            }

        except Exception as e:
            logger.error(
                f"Error generating user engagement report: {str(e)}", exc_info=True
            )
            return {"user_engagement": {"error": str(e)}}

    def _generate_skill_trends_report(self):
        """Generate skill trends and analytics."""
        try:
            # Most endorsed skills in period
            top_endorsed_skills = (
                Skill.objects.filter(endorsements__created_at__gte=self.start_date)
                .annotate(endorsement_count=Count("endorsements"))
                .order_by("-endorsement_count")[:20]
            )

            # Most popular skill categories
            popular_categories = (
                Skill.objects.values("category")
                .annotate(count=Count("category"))
                .order_by("-count")[:10]
            )

            # New skills added
            new_skills = Skill.objects.filter(created_at__gte=self.start_date).count()

            # Endorsement activity
            total_endorsements = SkillEndorsement.objects.filter(
                created_at__gte=self.start_date
            ).count()

            # Users by skill count
            skill_distribution = (
                User.objects.filter(status=User.UserStatus.ACTIVE)
                .annotate(skill_count=Count("skills"))
                .values("skill_count")
                .annotate(user_count=Count("id"))
                .order_by("skill_count")
            )

            # Top skill endorsers
            top_endorsers = (
                SkillEndorsement.objects.filter(created_at__gte=self.start_date)
                .values(
                    "endorser__username", "endorser__first_name", "endorser__last_name"
                )
                .annotate(endorsement_count=Count("id"))
                .order_by("-endorsement_count")[:10]
            )

            return {
                "skill_trends": {
                    "period": self.period,
                    "top_endorsed_skills": [
                        {
                            "name": skill.name,
                            "category": str(skill.category),
                            "endorsement_count": skill.endorsement_count,
                            "user": skill.user.get_full_name(),
                        }
                        for skill in top_endorsed_skills
                    ],
                    "popular_categories": list(popular_categories),
                    "new_skills_added": new_skills,
                    "total_endorsements": total_endorsements,
                    "skill_distribution": list(skill_distribution),
                    "top_endorsers": list(top_endorsers),
                }
            }

        except Exception as e:
            logger.error(
                f"Error generating skill trends report: {str(e)}", exc_info=True
            )
            return {"skill_trends": {"error": str(e)}}

    def _generate_network_growth_report(self):
        """Generate network growth analytics."""
        try:
            # Connection statistics
            new_connections = Connection.objects.filter(
                status=Connection.ConnectionStatus.ACCEPTED,
                updated_at__gte=self.start_date,
            ).count()

            pending_connections = Connection.objects.filter(
                status=Connection.ConnectionStatus.PENDING
            ).count()

            total_connections = Connection.objects.filter(
                status=Connection.ConnectionStatus.ACCEPTED
            ).count()

            # Follow statistics
            new_follows = Follow.objects.filter(created_at__gte=self.start_date).count()

            # Network membership statistics
            new_network_memberships = NetworkMembership.objects.filter(
                joined_at__gte=self.start_date,
                status=NetworkMembership.MembershipStatus.ACTIVE,
            ).count()

            # Most connected users
            most_connected = ProfileStats.objects.filter(
                user__status=User.UserStatus.ACTIVE
            ).order_by("-connections_count")[:10]

            # Most followed users
            most_followed = ProfileStats.objects.filter(
                user__status=User.UserStatus.ACTIVE
            ).order_by("-connections_count")[:10]

            # Network growth by day
            daily_growth = []
            current_date = self.start_date.date()
            while current_date <= self.end_date.date():
                daily_connections = Connection.objects.filter(
                    status=Connection.ConnectionStatus.ACCEPTED,
                    updated_at__date=current_date,
                ).count()
                daily_growth.append(
                    {
                        "date": current_date.isoformat(),
                        "new_connections": daily_connections,
                    }
                )
                current_date += timedelta(days=1)

            return {
                "network_growth": {
                    "period": self.period,
                    "new_connections": new_connections,
                    "pending_connections": pending_connections,
                    "total_connections": total_connections,
                    "new_follows": new_follows,
                    "new_network_memberships": new_network_memberships,
                    "most_connected_users": [
                        {
                            "user": stats.user.get_full_name(),
                            "username": stats.user.username,
                            "connections": stats.connections_count,
                        }
                        for stats in most_connected
                    ],
                    "most_followed_users": [
                        {
                            "user": stats.user.get_full_name(),
                            "username": stats.user.username,
                            "followers": stats.followers_count,
                        }
                        for stats in most_followed
                    ],
                    "daily_growth": daily_growth,
                }
            }

        except Exception as e:
            logger.error(
                f"Error generating network growth report: {str(e)}", exc_info=True
            )
            return {"network_growth": {"error": str(e)}}

    def _generate_profile_completeness_report(self):
        """Generate profile completeness analytics."""
        try:
            # Completeness distribution
            completeness_ranges = [
                (0, 20, "Very Low"),
                (21, 40, "Low"),
                (41, 60, "Medium"),
                (61, 80, "High"),
                (81, 100, "Very High"),
            ]

            completeness_distribution = {}
            active_users = User.objects.filter(status=User.UserStatus.ACTIVE)

            for min_val, max_val, label in completeness_ranges:
                # Calculate profile completeness on the fly
                count = 0
                for user in active_users:
                    completeness = self._calculate_profile_completeness(user)
                    if min_val <= completeness <= max_val:
                        count += 1
                completeness_distribution[label] = count

            # Average completeness
            total_completeness = 0
            user_count = 0
            for user in active_users:
                total_completeness += self._calculate_profile_completeness(user)
                user_count += 1

            avg_completeness = total_completeness / user_count if user_count > 0 else 0

            # Users with missing key information
            users_without_bio = User.objects.filter(
                bio="", status=User.UserStatus.ACTIVE
            ).count()

            users_without_experience = (
                User.objects.filter(
                    status=User.UserStatus.ACTIVE, experiences__isnull=True
                )
                .distinct()
                .count()
            )

            users_without_education = User.objects.filter(
                status=User.UserStatus.ACTIVE, educations__isnull=True
            ).count()

            users_without_skills = (
                User.objects.filter(status=User.UserStatus.ACTIVE, skills__isnull=True)
                .distinct()
                .count()
            )

            users_without_photo = User.objects.filter(
                profile_picture__isnull=True, status=User.UserStatus.ACTIVE
            ).count()

            # Profile improvement opportunities
            improvement_opportunities = {
                "users_without_bio": users_without_bio,
                "users_without_experience": users_without_experience,
                "users_without_education": users_without_education,
                "users_without_skills": users_without_skills,
                "users_without_photo": users_without_photo,
            }

            return {
                "profile_completeness": {
                    "period": self.period,
                    "average_completeness": round(avg_completeness, 2),
                    "completeness_distribution": completeness_distribution,
                    "improvement_opportunities": improvement_opportunities,
                }
            }

        except Exception as e:
            logger.error(
                f"Error generating profile completeness report: {str(e)}", exc_info=True
            )
            return {"profile_completeness": {"error": str(e)}}

    def _generate_system_usage_report(self):
        """Generate system usage analytics."""
        try:
            # Content statistics
            content_stats = {
                "total_experiences": Experience.objects.count(),
                "total_education": Education.objects.count(),
                "total_skills": Skill.objects.count(),
                "total_projects": Project.objects.count(),
                "total_certifications": Certification.objects.count(),
                "total_achievements": Achievement.objects.count(),
                "total_publications": Publication.objects.count(),
                "total_volunteer": Volunteer.objects.count(),
                "total_languages": Language.objects.count(),
                "total_resumes": Resume.objects.count(),
            }

            # New content in period
            new_content = {
                "new_experiences": Experience.objects.filter(
                    created_at__gte=self.start_date
                ).count(),
                "new_education": Education.objects.filter(
                    created_at__gte=self.start_date
                ).count(),
                "new_skills": Skill.objects.filter(
                    created_at__gte=self.start_date
                ).count(),
                "new_projects": Project.objects.filter(
                    created_at__gte=self.start_date
                ).count(),
                "new_certifications": Certification.objects.filter(
                    created_at__gte=self.start_date
                ).count(),
                "new_achievements": Achievement.objects.filter(
                    created_at__gte=self.start_date
                ).count(),
                "new_publications": Publication.objects.filter(
                    created_at__gte=self.start_date
                ).count(),
                "new_volunteer": Volunteer.objects.filter(
                    created_at__gte=self.start_date
                ).count(),
                "new_languages": Language.objects.filter(
                    created_at__gte=self.start_date
                ).count(),
                "new_resumes": Resume.objects.filter(
                    created_at__gte=self.start_date
                ).count(),
            }

            # Message statistics
            message_stats = {
                "total_messages": Message.objects.filter(
                    created_at__gte=self.start_date
                ).count(),
                "read_messages": Message.objects.filter(
                    created_at__gte=self.start_date, read_at__isnull=False
                ).count(),
            }

            # Task statistics
            task_stats = {
                "total_tasks": Task.objects.filter(
                    created_at__gte=self.start_date
                ).count(),
                "completed_tasks": Task.objects.filter(
                    created_at__gte=self.start_date, status=Task.TaskStatus.COMPLETED
                ).count(),
                "overdue_tasks": Task.objects.filter(
                    due_date__lt=timezone.now().date(),
                    status__in=[Task.TaskStatus.TODO, Task.TaskStatus.IN_PROGRESS],
                ).count(),
            }

            # File upload statistics
            file_stats = {
                "total_files": UserFile.objects.filter(
                    created_at__gte=self.start_date
                ).count(),
                "public_files": UserFile.objects.filter(
                    created_at__gte=self.start_date, is_public=True
                ).count(),
            }

            return {
                "system_usage": {
                    "period": self.period,
                    "content_statistics": content_stats,
                    "new_content": new_content,
                    "message_statistics": message_stats,
                    "task_statistics": task_stats,
                    "file_statistics": file_stats,
                }
            }

        except Exception as e:
            logger.error(
                f"Error generating system usage report: {str(e)}", exc_info=True
            )
            return {"system_usage": {"error": str(e)}}

    def _generate_admin_summary_report(self):
        """Generate summary report for administrators."""
        try:
            # System health indicators
            total_users = User.objects.count()
            active_users = User.objects.filter(status=User.UserStatus.ACTIVE).count()
            verified_users = User.objects.filter(is_verified=True).count()
            suspended_users = User.objects.filter(
                status=User.UserStatus.INACTIVE
            ).count()

            # Recent activity summary
            recent_activity = {
                "new_users_7d": User.objects.filter(
                    date_joined__gte=timezone.now() - timedelta(days=7)
                ).count(),
                "new_connections_7d": Connection.objects.filter(
                    status=Connection.ConnectionStatus.ACCEPTED,
                    updated_at__gte=timezone.now() - timedelta(days=7),
                ).count(),
                "new_endorsements_7d": SkillEndorsement.objects.filter(
                    created_at__gte=timezone.now() - timedelta(days=7)
                ).count(),
                "new_recommendations_7d": Recommendation.objects.filter(
                    created_at__gte=timezone.now() - timedelta(days=7),
                ).count(),
            }

            # Content moderation queue
            moderation_queue = {
                "pending_recommendations": Recommendation.objects.filter(
                    created_at__gte=timezone.now() - timedelta(days=30)
                ).count(),
                "recent_certifications": Certification.objects.filter(
                    created_at__gte=timezone.now() - timedelta(days=30)
                ).count(),
                "total_user_files": UserFile.objects.filter(
                    created_at__gte=timezone.now() - timedelta(days=30)
                ).count(),
                "pending_network_memberships": NetworkMembership.objects.filter(
                    status=NetworkMembership.MembershipStatus.PENDING
                ).count(),
            }

            # System performance indicators
            # Calculate average profile completeness manually
            active_users = User.objects.filter(status=User.UserStatus.ACTIVE)
            total_completeness = sum(
                self._calculate_profile_completeness(user) for user in active_users
            )
            avg_profile_completeness = (
                total_completeness / active_users.count()
                if active_users.count() > 0
                else 0
            )

            performance_indicators = {
                "avg_profile_completeness": avg_profile_completeness,
                "avg_connections_per_user": ProfileStats.objects.filter(
                    user__status=User.UserStatus.ACTIVE
                ).aggregate(avg=Avg("connections_count"))["avg"]
                or 0,
                "avg_endorsements_per_user": ProfileStats.objects.filter(
                    user__status=User.UserStatus.ACTIVE
                ).aggregate(avg=Avg("endorsements_count"))["avg"]
                or 0,
            }

            # Alerts and warnings
            alerts = []

            # Check for unusual activity
            if suspended_users > total_users * 0.05:  # More than 5% suspended
                alerts.append(
                    f"High suspension rate: {suspended_users} users suspended"
                )

            if active_users.count() < total_users * 0.7:  # Less than 70% active
                alerts.append(
                    f"Low activity rate: Only {active_users.count()}/{total_users} users active"
                )

            # Check for overdue tasks
            overdue_tasks = Task.objects.filter(
                due_date__lt=timezone.now().date(),
                status__in=[Task.TaskStatus.TODO, Task.TaskStatus.IN_PROGRESS],
            ).count()

            if overdue_tasks > 0:
                alerts.append(f"{overdue_tasks} overdue tasks need attention")

            return {
                "admin_summary": {
                    "generated_at": timezone.now().isoformat(),
                    "system_health": {
                        "total_users": total_users,
                        "active_users": active_users.count(),
                        "verified_users": verified_users,
                        "suspended_users": suspended_users,
                        "activity_rate": round(
                            (active_users.count() / max(total_users, 1)) * 100, 2
                        ),
                        "verification_rate": round(
                            (verified_users / max(total_users, 1)) * 100, 2
                        ),
                    },
                    "recent_activity": recent_activity,
                    "moderation_queue": moderation_queue,
                    "performance_indicators": {
                        "avg_profile_completeness": round(
                            performance_indicators["avg_profile_completeness"], 2
                        ),
                        "avg_connections_per_user": round(
                            performance_indicators["avg_connections_per_user"], 2
                        ),
                        "avg_endorsements_per_user": round(
                            performance_indicators["avg_endorsements_per_user"], 2
                        ),
                    },
                    "alerts": alerts,
                }
            }

        except Exception as e:
            logger.error(
                f"Error generating admin summary report: {str(e)}", exc_info=True
            )
            return {"admin_summary": {"error": str(e)}}

    def _output_reports(self, reports):
        """Output the reports in the specified format."""
        if self.output == "console":
            self._output_to_console(reports)
        elif self.output == "json":
            self._output_to_json(reports)
        elif self.output == "email":
            self._output_to_email(reports)

        if self.save_to_file:
            self._save_to_file(reports)

    def _output_to_console(self, reports):
        """Output reports to console."""
        for report_name, report_data in reports.items():
            self.stdout.write(f"\n{'=' * 50}")
            self.stdout.write(f"{report_name.upper().replace('_', ' ')} REPORT")
            self.stdout.write(f"{'=' * 50}")

            if "error" in report_data:
                self.stdout.write(self.style.ERROR(f"Error: {report_data['error']}"))
                continue

            self._print_dict(report_data, indent=0)

    def _output_to_json(self, reports):
        """Output reports as JSON."""

        # Convert any translation proxies to strings
        def serialize_json_safe(obj):
            if hasattr(obj, "__iter__") and not isinstance(obj, (str, bytes)):
                if isinstance(obj, dict):
                    return {str(k): serialize_json_safe(v) for k, v in obj.items()}
                elif isinstance(obj, (list, tuple)):
                    return [serialize_json_safe(item) for item in obj]
            return str(obj) if hasattr(obj, "_proxy____args") else obj

        safe_reports = serialize_json_safe(reports)
        json_output = json.dumps(safe_reports, indent=2, default=str)
        self.stdout.write(json_output)

    def _output_to_email(self, reports):
        """Send reports via email."""
        if not self.email:
            self.stdout.write(
                self.style.ERROR("Email address required for email output")
            )
            return

        try:
            subject = f"Profile System Analytics Report - {self.period.title()}"
            message = self._format_email_report(reports)

            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[self.email],
                fail_silently=False,
            )

            self.stdout.write(f"Report sent to {self.email}")

        except Exception as e:
            logger.error(f"Error sending email report: {str(e)}", exc_info=True)
            self.stdout.write(self.style.ERROR(f"Failed to send email: {str(e)}"))

    def _save_to_file(self, reports):
        """Save reports to file."""
        try:
            timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
            filename = f"profile_analytics_{self.period}_{timestamp}.json"

            with open(filename, "w") as f:
                json.dump(reports, f, indent=2, default=str)

            self.stdout.write(f"Report saved to {filename}")

        except Exception as e:
            logger.error(f"Error saving report to file: {str(e)}", exc_info=True)
            self.stdout.write(self.style.ERROR(f"Failed to save file: {str(e)}"))

    def _print_dict(self, data, indent=0):
        """Recursively print dictionary data with proper indentation."""
        indent_str = "  " * indent

        for key, value in data.items():
            if isinstance(value, dict):
                self.stdout.write(f"{indent_str}{key.title().replace('_', ' ')}:")
                self._print_dict(value, indent + 1)
            elif isinstance(value, list):
                self.stdout.write(f"{indent_str}{key.title().replace('_', ' ')}:")
                for i, item in enumerate(value[:5]):  # Limit to first 5 items
                    if isinstance(item, dict):
                        self.stdout.write(f"{indent_str}  {i + 1}.")
                        self._print_dict(item, indent + 2)
                    else:
                        self.stdout.write(f"{indent_str}  - {item}")
                if len(value) > 5:
                    self.stdout.write(f"{indent_str}  ... and {len(value) - 5} more")
            else:
                self.stdout.write(
                    f"{indent_str}{key.title().replace('_', ' ')}: {value}"
                )

    def _format_email_report(self, reports):
        """Format reports for email."""
        email_content = []
        email_content.append("Profile System Analytics Report")
        email_content.append(f"Period: {self.period.title()}")
        email_content.append(
            f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        email_content.append("=" * 50)

        for report_name, report_data in reports.items():
            email_content.append(f"\n{report_name.upper().replace('_', ' ')} REPORT")
            email_content.append("-" * 30)

            if "error" in report_data:
                email_content.append(f"Error: {report_data['error']}")
                continue

            self._format_dict_for_email(report_data, email_content, indent=0)

        return "\n".join(email_content)

    def _format_dict_for_email(self, data, content_list, indent=0):
        """Format dictionary data for email."""
        indent_str = "  " * indent

        for key, value in data.items():
            if isinstance(value, dict):
                content_list.append(f"{indent_str}{key.title().replace('_', ' ')}:")
                self._format_dict_for_email(value, content_list, indent + 1)
            elif isinstance(value, list):
                content_list.append(f"{indent_str}{key.title().replace('_', ' ')}:")
                for i, item in enumerate(value[:10]):  # Limit to first 10 items
                    if isinstance(item, dict):
                        # Format dict items compactly for email
                        item_str = ", ".join([f"{k}: {v}" for k, v in item.items()])
                        content_list.append(f"{indent_str}  {i + 1}. {item_str}")
                    else:
                        content_list.append(f"{indent_str}  - {item}")
                if len(value) > 10:
                    content_list.append(f"{indent_str}  ... and {len(value) - 10} more")
            else:
                content_list.append(
                    f"{indent_str}{key.title().replace('_', ' ')}: {value}"
                )

    def _detect_trending_topics(self):
        """Detect trending topics and skills."""
        try:
            # Most mentioned companies in recent experiences
            trending_companies = (
                Experience.objects.filter(created_at__gte=self.start_date)
                .values("company")
                .annotate(count=Count("company"))
                .order_by("-count")[:10]
            )

            # Most mentioned technologies in projects
            trending_techs = []
            recent_projects = Project.objects.filter(created_at__gte=self.start_date)

            tech_counts = {}
            for project in recent_projects:
                if project.technologies:
                    techs = [tech.strip() for tech in project.technologies.split(",")]
                    for tech in techs:
                        tech_counts[tech] = tech_counts.get(tech, 0) + 1

            trending_techs = sorted(
                tech_counts.items(), key=lambda x: x[1], reverse=True
            )[:10]

            # Most popular skill categories
            trending_skill_categories = (
                Skill.objects.filter(created_at__gte=self.start_date)
                .values("category")
                .annotate(count=Count("category"))
                .order_by("-count")[:10]
            )

            return {
                "trending_topics": {
                    "trending_companies": list(trending_companies),
                    "trending_technologies": trending_techs,
                    "trending_skill_categories": list(trending_skill_categories),
                }
            }

        except Exception as e:
            logger.error(f"Error detecting trending topics: {str(e)}", exc_info=True)
            return {"trending_topics": {"error": str(e)}}

    def _calculate_profile_completeness(self, user):
        """Calculate profile completeness percentage based on available fields."""
        score = 0
        total_fields = 10  # Total number of fields we're checking

        # Basic user info (3 points)
        if user.first_name:
            score += 1
        if user.last_name:
            score += 1
        if user.bio:
            score += 1

        # Profile info (3 points)
        try:
            profile = user.profile
            if profile.display_name:
                score += 1
            if profile.website:
                score += 1
            if user.profile_picture:
                score += 1
        except:
            pass

        # Professional info (4 points)
        if user.experiences.exists():
            score += 1
        if user.educations.exists():
            score += 1
        if user.skills.exists():
            score += 1
        if user.projects.exists():
            score += 1

        return (score / total_fields) * 100
