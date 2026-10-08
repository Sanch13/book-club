from django.apps import AppConfig


class ClubConfig(AppConfig):
    name = 'club'

    def ready(self):
        # Подключаем сигнал сжатия обложек
        from . import signals  # noqa: F401
