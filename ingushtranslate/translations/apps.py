from django.apps import AppConfig


class TranslationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "translations"
    verbose_name = "Предложения и переводы"

    def ready(self):
        import translations.signals
