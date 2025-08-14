from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"  # type: ignore
    name = "apps.accounts"
    verbose_name = "Accounts"

    def ready(self):
        """Import signals when the app is ready."""
        try:
            import apps.accounts.signals  # noqa
        except ImportError:
            pass
