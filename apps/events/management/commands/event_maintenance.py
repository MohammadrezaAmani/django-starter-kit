import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import models, transaction
from django.utils import timezone

from apps.events.models import (
    Event,
    EventAnalytics,
    EventTag,
    EventView,
    Participant,
    Session,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Perform maintenance tasks for events app"

    def add_arguments(self, parser):
        parser.add_argument(
            "--cleanup-expired",
            action="store_true",
            help="Clean up expired events and related data",
        )
        parser.add_argument(
            "--update-analytics",
            action="store_true",
            help="Update event analytics data",
        )
        parser.add_argument(
            "--update-trending",
            action="store_true",
            help="Update trending tags and events",
        )
        parser.add_argument(
            "--archive-old-events",
            action="store_true",
            help="Archive events older than specified days",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=365,
            help="Number of days for archiving old events (default: 365)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )

    def handle(self, *args, **options):
        self.dry_run = options["dry_run"]

        if self.dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be made")
            )

        if options["cleanup_expired"]:
            self.cleanup_expired_events()

        if options["update_analytics"]:
            self.update_event_analytics()

        if options["update_trending"]:
            self.update_trending_data()

        if options["archive_old_events"]:
            self.archive_old_events(options["days"])

        # If no specific task is specified, run all maintenance tasks
        if not any(
            [
                options["cleanup_expired"],
                options["update_analytics"],
                options["update_trending"],
                options["archive_old_events"],
            ]
        ):
            self.stdout.write("Running all maintenance tasks...")
            self.cleanup_expired_events()
            self.update_event_analytics()
            self.update_trending_data()
            self.archive_old_events(options["days"])

        self.stdout.write(
            self.style.SUCCESS("Event maintenance completed successfully")
        )

    def cleanup_expired_events(self):
        """Clean up expired events and related data."""
        self.stdout.write("Cleaning up expired events...")

        # Get events that ended more than 30 days ago
        cutoff_date = timezone.now() - timedelta(days=30)
        expired_events = Event.objects.filter(
            end_date__lt=cutoff_date, status__in=["completed", "cancelled"]
        )

        count = expired_events.count()
        if count == 0:
            self.stdout.write("No expired events to clean up")
            return

        self.stdout.write(f"Found {count} expired events")

        if not self.dry_run:
            with transaction.atomic():
                # Clean up old event views (keep only last 90 days)
                view_cutoff = timezone.now() - timedelta(days=90)
                old_views = EventView.objects.filter(
                    event__in=expired_events, created_at__lt=view_cutoff
                )
                view_count = old_views.count()
                old_views.delete()
                self.stdout.write(f"Deleted {view_count} old event views")

                # Archive participants from old events
                old_participants = Participant.objects.filter(
                    event__in=expired_events, event__end_date__lt=cutoff_date
                )
                participant_count = old_participants.count()

                # Instead of deleting, mark as archived
                old_participants.update(registration_status="archived")
                self.stdout.write(f"Archived {participant_count} old participants")

        self.stdout.write("Expired events cleanup completed")

    def update_event_analytics(self):
        """Update analytics data for all events."""
        self.stdout.write("Updating event analytics...")

        active_events = Event.objects.filter(
            status__in=["published", "live", "completed"]
        )

        updated_count = 0
        for event in active_events:
            if not self.dry_run:
                analytics, created = EventAnalytics.objects.get_or_create(event=event)

                # Update registration metrics
                participants = event.participants.all()
                analytics.total_registrations = participants.count()
                analytics.confirmed_attendees = participants.filter(
                    registration_status="confirmed"
                ).count()
                analytics.no_shows = participants.filter(
                    attendance_status="no_show"
                ).count()

                # Update view metrics
                analytics.total_views = event.views.count()
                analytics.unique_views = event.views.values("user").distinct().count()

                # Calculate engagement metrics
                if analytics.total_views > 0:
                    analytics.engagement_rate = (
                        analytics.total_registrations / analytics.total_views
                    ) * 100

                analytics.save()
                updated_count += 1

        self.stdout.write(f"Updated analytics for {updated_count} events")

    def update_trending_data(self):
        """Update trending tags and events."""
        self.stdout.write("Updating trending data...")

        # Update trending tags based on recent usage
        thirty_days_ago = timezone.now() - timedelta(days=30)

        if not self.dry_run:
            # Reset all trending flags
            EventTag.objects.update(is_trending=False)

            # Find tags used in recent events
            trending_tags = (
                EventTag.objects.filter(
                    events__created_at__gte=thirty_days_ago,
                    events__status__in=["published", "live"],
                )
                .annotate(recent_usage=models.Count("events"))
                .filter(
                    recent_usage__gte=3  # Used in at least 3 recent events
                )
                .order_by("-recent_usage")[:10]
            )

            # Mark as trending
            trending_tag_ids = list(trending_tags.values_list("id", flat=True))
            EventTag.objects.filter(id__in=trending_tag_ids).update(is_trending=True)

            self.stdout.write(f"Updated {len(trending_tag_ids)} trending tags")

        # Update event trending scores
        recent_events = Event.objects.filter(
            created_at__gte=thirty_days_ago, status__in=["published", "live"]
        )

        trending_count = 0
        for event in recent_events:
            if not self.dry_run:
                # Calculate trending score based on various factors
                views = event.views.count()
                registrations = event.participants.count()
                favorites = event.favorites.count()

                # Simple trending score calculation
                (views * 0.1) + (registrations * 2) + (favorites * 5)

                # Update the event's trending score (if field exists)
                # Note: This would require adding a trending_score field to Event model
                pass

            trending_count += 1

        self.stdout.write(f"Processed trending data for {trending_count} events")

    def archive_old_events(self, days):
        """Archive events older than specified days."""
        self.stdout.write(f"Archiving events older than {days} days...")

        cutoff_date = timezone.now() - timedelta(days=days)
        old_events = Event.objects.filter(
            end_date__lt=cutoff_date, status__in=["completed", "cancelled"]
        ).exclude(
            status="archived"  # Don't re-archive already archived events
        )

        count = old_events.count()
        if count == 0:
            self.stdout.write("No events to archive")
            return

        self.stdout.write(f"Found {count} events to archive")

        if not self.dry_run:
            with transaction.atomic():
                # Update event status to archived
                old_events.update(status="archived")

                # Archive related sessions
                Session.objects.filter(event__in=old_events).update(status="archived")

        self.stdout.write(f"Archived {count} old events")

    def cleanup_orphaned_data(self):
        """Clean up orphaned data without parent objects."""
        self.stdout.write("Cleaning up orphaned data...")

        if not self.dry_run:
            # Clean up event views for non-existent events
            orphaned_views = EventView.objects.filter(event__isnull=True)
            view_count = orphaned_views.count()
            orphaned_views.delete()

            # Clean up participants for non-existent events
            orphaned_participants = Participant.objects.filter(event__isnull=True)
            participant_count = orphaned_participants.count()
            orphaned_participants.delete()

            # Clean up sessions for non-existent events
            orphaned_sessions = Session.objects.filter(event__isnull=True)
            session_count = orphaned_sessions.count()
            orphaned_sessions.delete()

            self.stdout.write(
                f"Cleaned up {view_count} orphaned views, "
                f"{participant_count} orphaned participants, "
                f"{session_count} orphaned sessions"
            )

    def update_usage_counts(self):
        """Update usage counts for tags and categories."""
        self.stdout.write("Updating usage counts...")

        if not self.dry_run:
            # Update tag usage counts
            for tag in EventTag.objects.all():
                tag.usage_count = tag.events.filter(
                    status__in=["published", "live", "completed"]
                ).count()
                tag.save(update_fields=["usage_count"])

            self.stdout.write("Updated tag usage counts")

    def generate_report(self):
        """Generate a maintenance report."""
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("MAINTENANCE REPORT")
        self.stdout.write("=" * 50)

        # Event statistics
        total_events = Event.objects.count()
        active_events = Event.objects.filter(status__in=["published", "live"]).count()
        completed_events = Event.objects.filter(status="completed").count()

        self.stdout.write(f"Total Events: {total_events}")
        self.stdout.write(f"Active Events: {active_events}")
        self.stdout.write(f"Completed Events: {completed_events}")

        # Participant statistics
        total_participants = Participant.objects.count()
        confirmed_participants = Participant.objects.filter(
            registration_status="confirmed"
        ).count()

        self.stdout.write(f"Total Participants: {total_participants}")
        self.stdout.write(f"Confirmed Participants: {confirmed_participants}")

        # Tag statistics
        total_tags = EventTag.objects.count()
        trending_tags = EventTag.objects.filter(is_trending=True).count()

        self.stdout.write(f"Total Tags: {total_tags}")
        self.stdout.write(f"Trending Tags: {trending_tags}")

        # Recent activity (last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        recent_events = Event.objects.filter(created_at__gte=thirty_days_ago).count()
        recent_registrations = Participant.objects.filter(
            created_at__gte=thirty_days_ago
        ).count()

        self.stdout.write(f"Events Created (30 days): {recent_events}")
        self.stdout.write(f"New Registrations (30 days): {recent_registrations}")

        self.stdout.write("=" * 50)
