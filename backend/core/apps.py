from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "core"
    verbose_name = "VHS"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from core import checks  # noqa: F401  registers the system checks
