import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from apps.chats.models import (
    Chat,
    ChatAttachment,
    ChatBot,
    ChatCall,
    ChatMessage,
    ChatModerationLog,
    ChatParticipant,
    ChatPoll,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Generate comprehensive chat system statistics.
    """

    help = "Generate chat system statistics and reports"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Number of days to analyze (default: 30)",
        )
        parser.add_argument(
            "--detailed",
            action="store_true",
            help="Show detailed statistics",
        )
        parser.add_argument(
            "--export",
            type=str,
            help="Export to file (json/csv)",
        )
        parser.add_argument(
            "--chat-type",
            type=str,
            choices=[choice[0] for choice in Chat.ChatType.choices],
            help="Filter by chat type",
        )
        parser.add_argument(
            "--user-stats",
            action="store_true",
            help="Include user-specific statistics",
        )
        parser.add_argument(
            "--bot-stats",
            action="store_true",
            help="Include bot statistics",
        )

    def handle(self, *args, **options):
        """Main command handler."""
        self.verbosity = options["verbosity"]
        self.days = options["days"]
        self.detailed = options["detailed"]
        self.export = options.get("export")
        self.chat_type = options.get("chat_type")
        self.user_stats = options["user_stats"]
        self.bot_stats = options["bot_stats"]

        self.start_date = timezone.now() - timedelta(days=self.days)
        self.stats = {}

        self.stdout.write(
            self.style.SUCCESS(
                f"Generating chat statistics for the last {self.days} days"
            )
        )

        # Generate different types of statistics
        self._generate_basic_stats()
        self._generate_message_stats()
        self._generate_chat_stats()
        self._generate_user_activity_stats()

        if self.bot_stats:
            self._generate_bot_stats()

        if self.user_stats:
            self._generate_user_specific_stats()

        if self.detailed:
            self._generate_detailed_stats()

        # Display results
        self._display_stats()

        # Export if requested
        if self.export:
            self._export_stats()

        self.stdout.write(self.style.SUCCESS("Statistics generation completed"))

    def _generate_basic_stats(self):
        """Generate basic system statistics."""
        self.stdout.write("Generating basic statistics...")

        queryset = Chat.objects.all()
        if self.chat_type:
            queryset = queryset.filter(type=self.chat_type)

        recent_queryset = queryset.filter(created_at__gte=self.start_date)

        self.stats["basic"] = {
            "total_chats": queryset.count(),
            "new_chats": recent_queryset.count(),
            "active_chats": queryset.filter(status=Chat.ChatStatus.ACTIVE).count(),
            "public_chats": queryset.filter(is_public=True).count(),
            "encrypted_chats": queryset.filter(is_encrypted=True).count(),
        }

        # Chat type breakdown
        chat_types = {}
        for chat_type, label in Chat.ChatType.choices:
            count = queryset.filter(type=chat_type).count()
            chat_types[label] = count
        self.stats["basic"]["chat_types"] = chat_types

        # Total users and participants
        self.stats["basic"]["total_users"] = User.objects.count()
        self.stats["basic"]["total_participants"] = ChatParticipant.objects.filter(
            status=ChatParticipant.ParticipantStatus.ACTIVE
        ).count()

    def _generate_message_stats(self):
        """Generate message-related statistics."""
        self.stdout.write("Generating message statistics...")

        queryset = ChatMessage.objects.all()
        if self.chat_type:
            queryset = queryset.filter(chat__type=self.chat_type)

        recent_queryset = queryset.filter(created_at__gte=self.start_date)

        self.stats["messages"] = {
            "total_messages": queryset.count(),
            "recent_messages": recent_queryset.count(),
            "daily_average": (
                recent_queryset.count() / self.days if self.days > 0 else 0
            ),
        }

        # Message types breakdown
        message_types = {}
        for msg_type, label in ChatMessage.MessageType.choices:
            count = recent_queryset.filter(type=msg_type).count()
            if count > 0:
                message_types[label] = count
        self.stats["messages"]["message_types"] = message_types

        # Message status breakdown
        status_breakdown = {}
        for status, label in ChatMessage.MessageStatus.choices:
            count = recent_queryset.filter(status=status).count()
            if count > 0:
                status_breakdown[label] = count
        self.stats["messages"]["status_breakdown"] = status_breakdown

        # Media statistics
        media_messages = recent_queryset.filter(has_media=True)
        self.stats["messages"]["media_messages"] = media_messages.count()
        self.stats["messages"]["media_percentage"] = (
            (media_messages.count() / recent_queryset.count() * 100)
            if recent_queryset.count() > 0
            else 0
        )

        # Forwarded and edited messages
        self.stats["messages"]["forwarded_messages"] = recent_queryset.filter(
            is_forwarded=True
        ).count()
        self.stats["messages"]["edited_messages"] = recent_queryset.filter(
            edit_date__isnull=False
        ).count()

        # Reactions statistics
        messages_with_reactions = recent_queryset.exclude(reactions={})
        self.stats["messages"][
            "messages_with_reactions"
        ] = messages_with_reactions.count()

        total_reactions = 0
        for message in messages_with_reactions:
            for emoji, users in message.reactions.items():
                total_reactions += len(users)
        self.stats["messages"]["total_reactions"] = total_reactions

    def _generate_chat_stats(self):
        """Generate chat-specific statistics."""
        self.stdout.write("Generating chat statistics...")

        queryset = Chat.objects.all()
        if self.chat_type:
            queryset = queryset.filter(type=self.chat_type)

        # Participant statistics
        participant_stats = queryset.aggregate(
            avg_participants=Avg("participants_count"),
            total_participants=Sum("participants_count"),
        )

        self.stats["chats"] = {
            "average_participants": round(
                participant_stats["avg_participants"] or 0, 2
            ),
            "total_participant_slots": participant_stats["total_participants"] or 0,
        }

        # Most active chats
        active_chats = (
            queryset.annotate(
                recent_messages=Count(
                    "messages", filter=Q(messages__created_at__gte=self.start_date)
                )
            )
            .filter(recent_messages__gt=0)
            .order_by("-recent_messages")[:10]
        )

        self.stats["chats"]["most_active"] = [
            {
                "name": chat.name or str(chat.id)[:8],
                "type": chat.get_type_display(),
                "message_count": chat.recent_messages,
                "participants": chat.participants_count,
            }
            for chat in active_chats
        ]

        # Chat features usage
        features = {
            "ai_enabled": queryset.filter(ai_enabled=True).count(),
            "calls_enabled": queryset.filter(has_calls_enabled=True).count(),
            "video_calls_enabled": queryset.filter(
                has_video_calls_enabled=True
            ).count(),
            "protected_content": queryset.filter(has_protected_content=True).count(),
            "slow_mode": queryset.exclude(slow_mode_delay=0).count(),
        }
        self.stats["chats"]["features_usage"] = features

    def _generate_user_activity_stats(self):
        """Generate user activity statistics."""
        self.stdout.write("Generating user activity statistics...")

        # Active users (users who sent messages recently)
        active_users = User.objects.filter(
            sent_messages__created_at__gte=self.start_date
        ).distinct()

        self.stats["user_activity"] = {
            "active_users": active_users.count(),
            "activity_rate": (
                active_users.count() / User.objects.count() * 100
                if User.objects.count() > 0
                else 0
            ),
        }

        # Top message senders
        top_senders = (
            User.objects.annotate(
                recent_message_count=Count(
                    "sent_messages",
                    filter=Q(sent_messages__created_at__gte=self.start_date),
                )
            )
            .filter(recent_message_count__gt=0)
            .order_by("-recent_message_count")[:10]
        )

        self.stats["user_activity"]["top_senders"] = [
            {
                "username": user.username,
                "message_count": user.recent_message_count,
                "full_name": user.get_full_name(),
            }
            for user in top_senders
        ]

        # User roles distribution
        role_distribution = {}
        for role, label in ChatParticipant.ParticipantRole.choices:
            count = ChatParticipant.objects.filter(
                role=role, status=ChatParticipant.ParticipantStatus.ACTIVE
            ).count()
            if count > 0:
                role_distribution[label] = count
        self.stats["user_activity"]["role_distribution"] = role_distribution

    def _generate_bot_stats(self):
        """Generate bot-related statistics."""
        self.stdout.write("Generating bot statistics...")

        bots = ChatBot.objects.all()

        self.stats["bots"] = {
            "total_bots": bots.count(),
            "verified_bots": bots.filter(is_verified=True).count(),
            "inline_bots": bots.filter(is_inline=True).count(),
            "premium_bots": bots.filter(is_premium=True).count(),
        }

        # Bot activity
        bot_messages = ChatMessage.objects.filter(
            via_bot__isnull=False, created_at__gte=self.start_date
        )

        self.stats["bots"]["bot_messages"] = bot_messages.count()
        self.stats["bots"]["bot_message_percentage"] = (
            (
                bot_messages.count()
                / ChatMessage.objects.filter(created_at__gte=self.start_date).count()
                * 100
            )
            if ChatMessage.objects.filter(created_at__gte=self.start_date).count() > 0
            else 0
        )

        # Top bots by usage
        top_bots = (
            ChatBot.objects.annotate(
                recent_messages=Count(
                    "bot_messages",
                    filter=Q(bot_messages__created_at__gte=self.start_date),
                )
            )
            .filter(recent_messages__gt=0)
            .order_by("-recent_messages")[:5]
        )

        self.stats["bots"]["top_bots"] = [
            {
                "username": bot.user.username,
                "message_count": bot.recent_messages,
                "description": (
                    bot.description[:50] + "..."
                    if len(bot.description) > 50
                    else bot.description
                ),
            }
            for bot in top_bots
        ]

    def _generate_user_specific_stats(self):
        """Generate detailed user-specific statistics."""
        self.stdout.write("Generating user-specific statistics...")

        # User engagement metrics
        user_metrics = []
        active_users = User.objects.filter(
            sent_messages__created_at__gte=self.start_date
        ).distinct()[
            :20
        ]  # Limit to top 20 for performance

        for user in active_users:
            metrics = {
                "username": user.username,
                "full_name": user.get_full_name(),
                "messages_sent": user.sent_messages.filter(
                    created_at__gte=self.start_date
                ).count(),
                "chats_participated": ChatParticipant.objects.filter(
                    user=user, status=ChatParticipant.ParticipantStatus.ACTIVE
                ).count(),
                "reactions_given": 0,  # Would need to calculate from message reactions
                "calls_initiated": ChatCall.objects.filter(
                    initiator=user, start_time__gte=self.start_date
                ).count(),
            }
            user_metrics.append(metrics)

        self.stats["user_specific"] = {
            "top_users": sorted(
                user_metrics, key=lambda x: x["messages_sent"], reverse=True
            )[:10]
        }

    def _generate_detailed_stats(self):
        """Generate detailed statistics for comprehensive analysis."""
        self.stdout.write("Generating detailed statistics...")

        # Call statistics
        calls = ChatCall.objects.filter(start_time__gte=self.start_date)
        self.stats["calls"] = {
            "total_calls": calls.count(),
            "completed_calls": calls.filter(status=ChatCall.CallStatus.ENDED).count(),
            "missed_calls": calls.filter(status=ChatCall.CallStatus.MISSED).count(),
            "average_duration": calls.filter(
                status=ChatCall.CallStatus.ENDED
            ).aggregate(avg_duration=Avg("duration"))["avg_duration"]
            or 0,
        }

        # Poll statistics
        polls = ChatPoll.objects.filter(created_at__gte=self.start_date)
        self.stats["polls"] = {
            "total_polls": polls.count(),
            "quiz_polls": polls.filter(type=ChatPoll.PollType.QUIZ).count(),
            "anonymous_polls": polls.filter(is_anonymous=True).count(),
            "total_votes": polls.aggregate(total_votes=Sum("total_voter_count"))[
                "total_votes"
            ]
            or 0,
        }

        # Attachment statistics
        attachments = ChatAttachment.objects.filter(created_at__gte=self.start_date)
        self.stats["attachments"] = {
            "total_attachments": attachments.count(),
            "total_size_mb": round(
                (attachments.aggregate(total_size=Sum("file_size"))["total_size"] or 0)
                / (1024 * 1024),
                2,
            ),
        }

        # Attachment types breakdown
        attachment_types = {}
        for att_type, label in ChatAttachment.AttachmentType.choices:
            count = attachments.filter(type=att_type).count()
            if count > 0:
                attachment_types[label] = count
        self.stats["attachments"]["types"] = attachment_types

        # Moderation statistics
        mod_logs = ChatModerationLog.objects.filter(created_at__gte=self.start_date)
        self.stats["moderation"] = {
            "total_actions": mod_logs.count(),
            "user_bans": mod_logs.filter(
                action=ChatModerationLog.ActionType.BAN_USER
            ).count(),
            "message_deletions": mod_logs.filter(
                action=ChatModerationLog.ActionType.DELETE_MESSAGE
            ).count(),
            "promotions": mod_logs.filter(
                action=ChatModerationLog.ActionType.PROMOTE_USER
            ).count(),
        }

    def _display_stats(self):
        """Display statistics in a formatted way."""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("CHAT SYSTEM STATISTICS"))
        self.stdout.write("=" * 60)

        # Basic statistics
        if "basic" in self.stats:
            self.stdout.write(self.style.HTTP_INFO("\n📊 BASIC STATISTICS"))
            basic = self.stats["basic"]
            self.stdout.write(f"Total Chats: {basic['total_chats']}")
            self.stdout.write(
                f"New Chats (last {self.days} days): {basic['new_chats']}"
            )
            self.stdout.write(f"Active Chats: {basic['active_chats']}")
            self.stdout.write(f"Public Chats: {basic['public_chats']}")
            self.stdout.write(f"Encrypted Chats: {basic['encrypted_chats']}")
            self.stdout.write(f"Total Users: {basic['total_users']}")
            self.stdout.write(f"Total Participants: {basic['total_participants']}")

            self.stdout.write("\nChat Types:")
            for chat_type, count in basic["chat_types"].items():
                self.stdout.write(f"  - {chat_type}: {count}")

        # Message statistics
        if "messages" in self.stats:
            self.stdout.write(self.style.HTTP_INFO("\n💬 MESSAGE STATISTICS"))
            messages = self.stats["messages"]
            self.stdout.write(f"Total Messages: {messages['total_messages']}")
            self.stdout.write(f"Recent Messages: {messages['recent_messages']}")
            self.stdout.write(f"Daily Average: {messages['daily_average']:.1f}")
            self.stdout.write(
                f"Media Messages: {messages['media_messages']} ({messages['media_percentage']:.1f}%)"
            )
            self.stdout.write(f"Forwarded Messages: {messages['forwarded_messages']}")
            self.stdout.write(f"Edited Messages: {messages['edited_messages']}")
            self.stdout.write(
                f"Messages with Reactions: {messages['messages_with_reactions']}"
            )
            self.stdout.write(f"Total Reactions: {messages['total_reactions']}")

            if messages["message_types"]:
                self.stdout.write("\nMessage Types:")
                for msg_type, count in messages["message_types"].items():
                    self.stdout.write(f"  - {msg_type}: {count}")

        # Chat statistics
        if "chats" in self.stats:
            self.stdout.write(self.style.HTTP_INFO("\n🏠 CHAT STATISTICS"))
            chats = self.stats["chats"]
            self.stdout.write(
                f"Average Participants per Chat: {chats['average_participants']}"
            )
            self.stdout.write(
                f"Total Participant Slots: {chats['total_participant_slots']}"
            )

            if chats["most_active"]:
                self.stdout.write("\nMost Active Chats:")
                for i, chat in enumerate(chats["most_active"], 1):
                    self.stdout.write(
                        f"  {i}. {chat['name']} ({chat['type']}) - "
                        f"{chat['message_count']} messages, {chat['participants']} participants"
                    )

        # User activity
        if "user_activity" in self.stats:
            self.stdout.write(self.style.HTTP_INFO("\n👥 USER ACTIVITY"))
            activity = self.stats["user_activity"]
            self.stdout.write(f"Active Users: {activity['active_users']}")
            self.stdout.write(f"Activity Rate: {activity['activity_rate']:.1f}%")

            if activity["top_senders"]:
                self.stdout.write("\nTop Message Senders:")
                for i, user in enumerate(activity["top_senders"], 1):
                    self.stdout.write(
                        f"  {i}. {user['full_name']} (@{user['username']}) - "
                        f"{user['message_count']} messages"
                    )

        # Bot statistics
        if "bots" in self.stats:
            self.stdout.write(self.style.HTTP_INFO("\n🤖 BOT STATISTICS"))
            bots = self.stats["bots"]
            self.stdout.write(f"Total Bots: {bots['total_bots']}")
            self.stdout.write(f"Verified Bots: {bots['verified_bots']}")
            self.stdout.write(f"Inline Bots: {bots['inline_bots']}")
            self.stdout.write(
                f"Bot Messages: {bots['bot_messages']} ({bots['bot_message_percentage']:.1f}%)"
            )

        # Detailed statistics
        if self.detailed:
            if "calls" in self.stats:
                self.stdout.write(self.style.HTTP_INFO("\n📞 CALL STATISTICS"))
                calls = self.stats["calls"]
                self.stdout.write(f"Total Calls: {calls['total_calls']}")
                self.stdout.write(f"Completed Calls: {calls['completed_calls']}")
                self.stdout.write(f"Missed Calls: {calls['missed_calls']}")
                self.stdout.write(
                    f"Average Duration: {calls['average_duration']:.1f} seconds"
                )

            if "attachments" in self.stats:
                self.stdout.write(self.style.HTTP_INFO("\n📎 ATTACHMENT STATISTICS"))
                attachments = self.stats["attachments"]
                self.stdout.write(
                    f"Total Attachments: {attachments['total_attachments']}"
                )
                self.stdout.write(f"Total Size: {attachments['total_size_mb']} MB")

    def _export_stats(self):
        """Export statistics to file."""
        import csv
        import json
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if self.export.lower() == "json":
            filename = f"chat_stats_{timestamp}.json"
            with open(filename, "w") as f:
                json.dump(self.stats, f, indent=2, default=str)
            self.stdout.write(f"Statistics exported to {filename}")

        elif self.export.lower() == "csv":
            filename = f"chat_stats_{timestamp}.csv"
            with open(filename, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Metric", "Value"])

                # Flatten stats for CSV
                for category, data in self.stats.items():
                    if isinstance(data, dict):
                        for key, value in data.items():
                            if isinstance(value, (int, float, str)):
                                writer.writerow([f"{category}_{key}", value])

            self.stdout.write(f"Statistics exported to {filename}")
