from django.apps import AppConfig


class CourseConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.course"
    verbose_name = "Course Management"

    def ready(self):
        """Import signals when the app is ready"""
