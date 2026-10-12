"""Общая настройка pytest.

Собираем статику один раз до прог��на. Причина: pytest-django форсирует
DEBUG=False, а с ManifestStaticFilesStorage (см. STORAGES в
src/config/settings.py) тег {% static %} читает манифест из STATIC_ROOT.
Без collectstatic любой рендер страницы со {% static %} падает с
ValueError: Missing staticfiles manifest entry — то есть тесты, которые
сейчас проходят, сломались бы все разом.

Побочная польза, ради которой фикстура и нужна в первую очередь:
collectstatic НЕ проверяет {% static %} в шаблонах. Страница может
ссылаться на несуществующий файл — сборка статики пройдёт молча, и без
этой фикстуры ошибка обнаружилась бы только на проде. С манифестом
рендер в тестах падает сразу, и тест краснеет.
"""

import pytest
from django.core.management import call_command


@pytest.fixture(scope='session', autouse=True)
def collect_static_once():
    """Собирает статику один раз на всю сессию тестов."""
    call_command('collectstatic', interactive=False, verbosity=0)