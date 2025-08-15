import logging
from datetime import timedelta

from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.utils import timezone

from apps.chats.models import (
    Chat,
    ChatAttachment,
    ChatCall,
    ChatInviteLink,
    ChatJoinRequest,
    ChatMessage,
    ChatModerationLog,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Cleanup command for chat system.
    Removes expired messages, inactive chats, old logs, etc.
    """

    help = "Clean up expired chat data and optimize database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Number of days to keep old data (default: 30)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )
        parser.add_argument(
            "--clean-messages",
            action="store_true",
            help="Clean up expired messages",
        )
        parser.add_argument(
            "--clean-chats",
            action="store_true",
            help="Clean up inactive chats",
        )
        parser.add_argument(
            "--clean-attachments",
            action="store_true",
            help="Clean up orphaned attachments",
        )
        parser.add_argument(
            "--clean-logs",
            action="store_true",
            help="Clean up old moderation logs",
        )
        parser.add_argument(
            "--clean-calls",
            action="store_true",
            help="Clean up old call records",
        )
        parser.add_argument(
            "--clean-requests",
            action="store_true",
            help="Clean up old join requests",
        )
        parser.add_argument(
            "--clean-links",
            action="store_true",
            help="Clean up expired invite links",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Run all cleanup operations",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force cleanup even if recently run",
        )

    def handle(self, *args, **options):
        """Main command handler."""
        self.verbosity = options["verbosity"]
        self.dry_run = options["dry_run"]
        self.days = options["days"]
        self.force = options["force"]

        # Check if cleanup was recently run
        if not self.force and self._was_recently_run():
            self.stdout.write(
                self.style.WARNING("Cleanup was run recently. Use --force to override.")
            )
            return

        self.stdout.write(
            self.style.SUCCESS(f"Starting chat cleanup (keeping last {self.days} days)")
        )

        total_cleaned = 0

        if options["all"] or options["clean_messages"]:
            total_cleaned += self._clean_expired_messages()

        if options["all"] or options["clean_chats"]:
            total_cleaned += self._clean_inactive_chats()

        if options["all"] or options["clean_attachments"]:
            total_cleaned += self._clean_orphaned_attachments()

        if options["all"] or options["clean_logs"]:
            total_cleaned += self._clean_old_logs()

        if options["all"] or options["clean_calls"]:
            total_cleaned += self._clean_old_calls()

        if options["all"] or options["clean_requests"]:
            total_cleaned += self._clean_old_requests()

        if options["all"] or options["clean_links"]:
            total_cleaned += self._clean_expired_links()

        if not any(
            [
                options["all"],
                options["clean_messages"],
                options["clean_chats"],
                options["clean_attachments"],
                options["clean_logs"],
                options["clean_calls"],
                options["clean_requests"],
                options["clean_links"],
            ]
        ):
            self.stdout.write(
                self.style.ERROR(
                    "Please specify what to clean or use --all. Run with --help for options."
                )
            )
            return

        # Update last run timestamp
        if not self.dry_run:
            self._update_last_run()

        self.stdout.write(
            self.style.SUCCESS(
                f"Cleanup completed. Total items processed: {total_cleaned}"
            )
        )

    def _was_recently_run(self):
        """Check if cleanup was run in the last 12 hours."""
        last_run = cache.get("chat_cleanup_last_run")
        if last_run:
            time_since = timezone.now() - last_run
            return time_since < timedelta(hours=12)
        return False

    def _update_last_run(self):
        """Update last run timestamp."""
        cache.set("chat_cleanup_last_run", timezone.now(), 86400)  # 24 hours

    def _clean_expired_messages(self):
        """Clean up expired messages."""
        self.stdout.write("Cleaning expired messages...")

        # Messages with TTL that have expired
        expired_messages = ChatMessage.objects.filter(
            auto_delete_date__lt=timezone.now(),
            status__in=[
                ChatMessage.MessageStatus.SENT,
                ChatMessage.MessageStatus.DELIVERED,
                ChatMessage.MessageStatus.READ,
            ],
        )

        count = expired_messages.count()
        if count > 0:
            self._log_action(f"Found {count} expired messages")
            if not self.dry_run:
                # Soft delete instead of hard delete
                expired_messages.update(
                    status=ChatMessage.MessageStatus.DELETED,
                    deleted_at=timezone.now(),
                    content="[Message expired]",
                )
                self._log_action(f"Soft deleted {count} expired messages")
        else:
            self._log_action("No expired messages found")

        # Old deleted messages (hard delete after 7 days)
        old_deleted = ChatMessage.objects.filter(
            status=ChatMessage.MessageStatus.DELETED,
            deleted_at__lt=timezone.now() - timedelta(days=7),
        )

        old_count = old_deleted.count()
        if old_count > 0:
            self._log_action(f"Found {old_count} old deleted messages for removal")
            if not self.dry_run:
                old_deleted.delete()
                self._log_action(f"Hard deleted {old_count} old messages")

        return count + old_count

    def _clean_inactive_chats(self):
        """Clean up inactive chats."""
        self.stdout.write("Cleaning inactive chats...")

        cutoff_date = timezone.now() - timedelta(days=self.days)

        # Find chats with no recent activity and no participants
        inactive_chats = (
            Chat.objects.filter(
                Q(updated_at__lt=cutoff_date)
                & Q(status=Chat.ChatStatus.DELETED)
                & Q(participants_count=0)
            )
            .annotate(
                recent_messages=Count(
                    "messages", filter=Q(messages__created_at__gte=cutoff_date)
                )
            )
            .filter(recent_messages=0)
        )

        count = inactive_chats.count()
        if count > 0:
            self._log_action(f"Found {count} inactive chats")
            if not self.dry_run:
                inactive_chats.delete()
                self._log_action(f"Deleted {count} inactive chats")
        else:
            self._log_action("No inactive chats found")

        return count

    def _clean_orphaned_attachments(self):
        """Clean up orphaned attachments."""
        self.stdout.write("Cleaning orphaned attachments...")

        # Attachments without messages
        orphaned = ChatAttachment.objects.filter(message__isnull=True)
        count = orphaned.count()

        if count > 0:
            self._log_action(f"Found {count} orphaned attachments")
            if not self.dry_run:
                # Delete files and database records
                for attachment in orphaned:
                    try:
                        if attachment.file:
                            attachment.file.delete(save=False)
                        if attachment.thumbnail:
                            attachment.thumbnail.delete(save=False)
                    except Exception as e:
                        logger.warning(f"Error deleting attachment file: {e}")

                orphaned.delete()
                self._log_action(f"Deleted {count} orphaned attachments")
        else:
            self._log_action("No orphaned attachments found")

        return count

    def _clean_old_logs(self):
        """Clean up old moderation logs."""
        self.stdout.write("Cleaning old moderation logs...")

        cutoff_date = timezone.now() - timedelta(days=self.days * 2)  # Keep logs longer
        old_logs = ChatModerationLog.objects.filter(created_at__lt=cutoff_date)

        count = old_logs.count()
        if count > 0:
            self._log_action(f"Found {count} old moderation logs")
            if not self.dry_run:
                old_logs.delete()
                self._log_action(f"Deleted {count} old moderation logs")
        else:
            self._log_action("No old moderation logs found")

        return count

    def _clean_old_calls(self):
        """Clean up old call records."""
        self.stdout.write("Cleaning old call records...")

        cutoff_date = timezone.now() - timedelta(days=self.days)
        old_calls = ChatCall.objects.filter(
            start_time__lt=cutoff_date,
            status__in=[
                ChatCall.CallStatus.ENDED,
                ChatCall.CallStatus.MISSED,
                ChatCall.CallStatus.DECLINED,
                ChatCall.CallStatus.FAILED,
            ],
        )

        count = old_calls.count()
        if count > 0:
            self._log_action(f"Found {count} old call records")
            if not self.dry_run:
                # Delete recording files before deleting records
                for call in old_calls:
                    if call.recording_file:
                        try:
                            call.recording_file.delete(save=False)
                        except Exception as e:
                            logger.warning(f"Error deleting call recording: {e}")

                old_calls.delete()
                self._log_action(f"Deleted {count} old call records")
        else:
            self._log_action("No old call records found")

        return count

    def _clean_old_requests(self):
        """Clean up old join requests."""
        self.stdout.write("Cleaning old join requests...")

        cutoff_date = timezone.now() - timedelta(days=self.days)
        old_requests = ChatJoinRequest.objects.filter(
            created_at__lt=cutoff_date,
            status__in=[
                ChatJoinRequest.RequestStatus.APPROVED,
                ChatJoinRequest.RequestStatus.DECLINED,
            ],
        )

        count = old_requests.count()
        if count > 0:
            self._log_action(f"Found {count} old join requests")
            if not self.dry_run:
                old_requests.delete()
                self._log_action(f"Deleted {count} old join requests")
        else:
            self._log_action("No old join requests found")

        return count

    def _clean_expired_links(self):
        """Clean up expired invite links."""
        self.stdout.write("Cleaning expired invite links...")

        now = timezone.now()
        expired_links = ChatInviteLink.objects.filter(
            Q(expire_date__lt=now)
            | Q(is_revoked=True, revoked_at__lt=now - timedelta(days=7))
        )

        count = expired_links.count()
        if count > 0:
            self._log_action(f"Found {count} expired invite links")
            if not self.dry_run:
                expired_links.delete()
                self._log_action(f"Deleted {count} expired invite links")
        else:
            self._log_action("No expired invite links found")

        return count

    def _log_action(self, message):
        """Log action with appropriate verbosity."""
        if self.verbosity >= 2:
            self.stdout.write(f"  {message}")
        logger.info(f"Chat cleanup: {message}")
