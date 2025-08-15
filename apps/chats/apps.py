from django.apps import AppConfig


class ChatsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.chats"
    verbose_name = "Chat System"

    def ready(self):
        """Import signals when Django starts."""
        import apps.chats.signals  # noqa
