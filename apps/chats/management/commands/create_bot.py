import hashlib
import logging
import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.chats.models import ChatBot

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Create and manage chat bots.
    """

    help = "Create and manage chat bots"

    def add_arguments(self, parser):
        parser.add_argument(
            "action",
            choices=["create", "list", "delete", "regenerate-token", "update"],
            help="Action to perform",
        )
        parser.add_argument(
            "--username",
            type=str,
            help="Bot username (required for create, delete, regenerate-token, update)",
        )
        parser.add_argument(
            "--name",
            type=str,
            help="Bot display name (for create/update)",
        )
        parser.add_argument(
            "--email",
            type=str,
            help="Bot email (for create)",
        )
        parser.add_argument(
            "--description",
            type=str,
            help="Bot description (for create/update)",
        )
        parser.add_argument(
            "--about",
            type=str,
            help="Bot about text (for create/update)",
        )
        parser.add_argument(
            "--commands",
            type=str,
            nargs="*",
            help="Bot commands in format 'command:description' (for create/update)",
        )
        parser.add_argument(
            "--inline",
            action="store_true",
            help="Enable inline mode (for create/update)",
        )
        parser.add_argument(
            "--can-join-groups",
            action="store_true",
            default=True,
            help="Allow bot to join groups (for create/update)",
        )
        parser.add_argument(
            "--can-read-all",
            action="store_true",
            help="Allow bot to read all group messages (for create/update)",
        )
        parser.add_argument(
            "--webhook-url",
            type=str,
            help="Bot webhook URL (for create/update)",
        )
        parser.add_argument(
            "--verified",
            action="store_true",
            help="Mark bot as verified (for create/update)",
        )
        parser.add_argument(
            "--premium",
            action="store_true",
            help="Mark bot as premium (for create/update)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force action without confirmation",
        )

    def handle(self, *args, **options):
        """Main command handler."""
        self.verbosity = options["verbosity"]
        self.force = options["force"]

        action = options["action"]

        if action == "create":
            self._create_bot(options)
        elif action == "list":
            self._list_bots(options)
        elif action == "delete":
            self._delete_bot(options)
        elif action == "regenerate-token":
            self._regenerate_token(options)
        elif action == "update":
            self._update_bot(options)

    def _create_bot(self, options):
        """Create a new bot."""
        username = options.get("username")
        if not username:
            raise CommandError("Username is required for creating a bot")

        # Validate username
        if not username.endswith("bot"):
            if not self.force:
                confirm = input(
                    f"Username '{username}' doesn't end with 'bot'. Continue? [y/N]: "
                )
                if confirm.lower() != "y":
                    self.stdout.write("Bot creation cancelled")
                    return
            username = f"{username}bot"

        # Check if user already exists
        if User.objects.filter(username=username).exists():
            raise CommandError(f"User with username '{username}' already exists")

        name = options.get("name") or username.replace("bot", "").title()
        email = options.get("email") or f"{username}@chatbot.local"
        description = options.get("description") or f"A helpful bot named {name}"
        about = options.get("about") or f"Bot: {name}"

        # Parse commands
        commands = []
        if options.get("commands"):
            for cmd in options["commands"]:
                if ":" in cmd:
                    command, desc = cmd.split(":", 1)
                    commands.append(
                        {"command": command.strip(), "description": desc.strip()}
                    )
                else:
                    commands.append(
                        {
                            "command": cmd.strip(),
                            "description": f"Execute {cmd.strip()}",
                        }
                    )

        # Add default commands if none provided
        if not commands:
            commands = [
                {"command": "/start", "description": "Start the bot"},
                {"command": "/help", "description": "Show help message"},
            ]

        try:
            with transaction.atomic():
                # Create user
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    first_name=name,
                    is_active=True,
                    is_bot=True,  # Assuming your User model has is_bot field
                )

                # Generate bot token
                bot_id = user.id
                token_part = secrets.token_urlsafe(32)
                token = f"{bot_id}:{token_part}"
                token_hash = hashlib.sha256(token.encode()).hexdigest()

                # Create bot profile
                bot = ChatBot.objects.create(
                    user=user,
                    description=description,
                    about=about,
                    token=token,
                    token_hash=token_hash,
                    commands=commands,
                    is_inline=options.get("inline", False),
                    can_join_groups=options.get("can_join_groups", True),
                    can_read_all_group_messages=options.get("can_read_all", False),
                    supports_inline_queries=options.get("inline", False),
                    webhook_url=options.get("webhook_url", ""),
                    is_verified=options.get("verified", False),
                    is_premium=options.get("premium", False),
                )

                self.stdout.write(
                    self.style.SUCCESS(f"✅ Bot '{username}' created successfully!")
                )
                self.stdout.write(f"Bot ID: {bot.user.id}")
                self.stdout.write(f"Token: {token}")
                self.stdout.write(
                    self.style.WARNING(
                        "⚠️  Save this token securely! It won't be shown again."
                    )
                )

                if self.verbosity >= 2:
                    self._display_bot_info(bot)

        except Exception as e:
            logger.error(f"Error creating bot: {e}")
            raise CommandError(f"Failed to create bot: {e}")

    def _list_bots(self, options):
        """List all bots."""
        bots = ChatBot.objects.select_related("user").all()

        if not bots.exists():
            self.stdout.write("No bots found")
            return

        self.stdout.write(f"\n📋 Found {bots.count()} bot(s):")
        self.stdout.write("-" * 80)

        for bot in bots:
            status_icons = []
            if bot.is_verified:
                status_icons.append("✅")
            if bot.is_premium:
                status_icons.append("⭐")
            if bot.is_inline:
                status_icons.append("🔍")
            if not bot.user.is_active:
                status_icons.append("❌")

            status = " ".join(status_icons) if status_icons else "🤖"

            self.stdout.write(f"{status} @{bot.user.username} (ID: {bot.user.id})")
            if self.verbosity >= 2:
                self.stdout.write(f"   Description: {bot.description}")
                self.stdout.write(f"   Messages sent: {bot.messages_sent}")
                self.stdout.write(f"   Users: {bot.users_count}")
                self.stdout.write(
                    f"   Created: {bot.created_at.strftime('%Y-%m-%d %H:%M')}"
                )
            self.stdout.write("")

    def _delete_bot(self, options):
        """Delete a bot."""
        username = options.get("username")
        if not username:
            raise CommandError("Username is required for deleting a bot")

        try:
            bot = ChatBot.objects.select_related("user").get(user__username=username)
        except ChatBot.DoesNotExist:
            raise CommandError(f"Bot with username '{username}' not found")

        if not self.force:
            self.stdout.write(f"🤖 Bot: @{bot.user.username}")
            self.stdout.write(f"   Description: {bot.description}")
            self.stdout.write(f"   Messages sent: {bot.messages_sent}")
            self.stdout.write(f"   Users: {bot.users_count}")

            confirm = input(
                f"\n⚠️  Are you sure you want to delete bot '@{username}'? "
                "This action cannot be undone. [y/N]: "
            )
            if confirm.lower() != "y":
                self.stdout.write("Bot deletion cancelled")
                return

        try:
            with transaction.atomic():
                user = bot.user
                bot.delete()
                user.delete()

                self.stdout.write(
                    self.style.SUCCESS(f"✅ Bot '@{username}' deleted successfully")
                )

        except Exception as e:
            logger.error(f"Error deleting bot: {e}")
            raise CommandError(f"Failed to delete bot: {e}")

    def _regenerate_token(self, options):
        """Regenerate bot token."""
        username = options.get("username")
        if not username:
            raise CommandError("Username is required for regenerating token")

        try:
            bot = ChatBot.objects.select_related("user").get(user__username=username)
        except ChatBot.DoesNotExist:
            raise CommandError(f"Bot with username '{username}' not found")

        if not self.force:
            confirm = input(
                f"⚠️  Regenerate token for bot '@{username}'? "
                "This will invalidate the current token. [y/N]: "
            )
            if confirm.lower() != "y":
                self.stdout.write("Token regeneration cancelled")
                return

        try:
            new_token = bot.generate_token()
            self.stdout.write(
                self.style.SUCCESS(f"✅ New token generated for '@{username}'")
            )
            self.stdout.write(f"Token: {new_token}")
            self.stdout.write(
                self.style.WARNING(
                    "⚠️  Save this token securely! It won't be shown again."
                )
            )

        except Exception as e:
            logger.error(f"Error regenerating token: {e}")
            raise CommandError(f"Failed to regenerate token: {e}")

    def _update_bot(self, options):
        """Update bot settings."""
        username = options.get("username")
        if not username:
            raise CommandError("Username is required for updating a bot")

        try:
            bot = ChatBot.objects.select_related("user").get(user__username=username)
        except ChatBot.DoesNotExist:
            raise CommandError(f"Bot with username '{username}' not found")

        updated_fields = []

        # Update basic info
        if options.get("name"):
            bot.user.first_name = options["name"]
            bot.user.save(update_fields=["first_name"])
            updated_fields.append("name")

        if options.get("description"):
            bot.description = options["description"]
            updated_fields.append("description")

        if options.get("about"):
            bot.about = options["about"]
            updated_fields.append("about")

        # Update commands
        if options.get("commands"):
            commands = []
            for cmd in options["commands"]:
                if ":" in cmd:
                    command, desc = cmd.split(":", 1)
                    commands.append(
                        {"command": command.strip(), "description": desc.strip()}
                    )
                else:
                    commands.append(
                        {
                            "command": cmd.strip(),
                            "description": f"Execute {cmd.strip()}",
                        }
                    )
            bot.commands = commands
            updated_fields.append("commands")

        # Update settings
        if "inline" in options:
            bot.is_inline = options["inline"]
            bot.supports_inline_queries = options["inline"]
            updated_fields.extend(["inline mode", "inline queries"])

        if "can_join_groups" in options:
            bot.can_join_groups = options["can_join_groups"]
            updated_fields.append("group joining")

        if "can_read_all" in options:
            bot.can_read_all_group_messages = options["can_read_all"]
            updated_fields.append("group message reading")

        if options.get("webhook_url"):
            bot.webhook_url = options["webhook_url"]
            updated_fields.append("webhook URL")

        if "verified" in options:
            bot.is_verified = options["verified"]
            updated_fields.append("verification status")

        if "premium" in options:
            bot.is_premium = options["premium"]
            updated_fields.append("premium status")

        if updated_fields:
            bot.save()
            self.stdout.write(
                self.style.SUCCESS(f"✅ Bot '@{username}' updated successfully")
            )
            self.stdout.write(f"Updated: {', '.join(updated_fields)}")

            if self.verbosity >= 2:
                self._display_bot_info(bot)
        else:
            self.stdout.write("No changes specified")

    def _display_bot_info(self, bot):
        """Display detailed bot information."""
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(f"🤖 Bot Information: @{bot.user.username}")
        self.stdout.write("=" * 50)
        self.stdout.write(f"ID: {bot.user.id}")
        self.stdout.write(f"Name: {bot.user.first_name}")
        self.stdout.write(f"Description: {bot.description}")
        self.stdout.write(f"About: {bot.about}")
        self.stdout.write(f"Inline Mode: {'✅' if bot.is_inline else '❌'}")
        self.stdout.write(f"Can Join Groups: {'✅' if bot.can_join_groups else '❌'}")
        self.stdout.write(
            f"Can Read All Messages: {'✅' if bot.can_read_all_group_messages else '❌'}"
        )
        self.stdout.write(f"Verified: {'✅' if bot.is_verified else '❌'}")
        self.stdout.write(f"Premium: {'✅' if bot.is_premium else '❌'}")
        self.stdout.write(f"Webhook URL: {bot.webhook_url or 'Not set'}")
        self.stdout.write(f"Messages Sent: {bot.messages_sent}")
        self.stdout.write(f"Users Count: {bot.users_count}")
        self.stdout.write(f"Created: {bot.created_at.strftime('%Y-%m-%d %H:%M:%S')}")

        if bot.commands:
            self.stdout.write("\nCommands:")
            for cmd in bot.commands:
                self.stdout.write(
                    f"  {cmd.get('command', 'N/A')} - {cmd.get('description', 'N/A')}"
                )

        self.stdout.write("=" * 50)
