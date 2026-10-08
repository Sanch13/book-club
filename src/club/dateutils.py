"""Форматирование дат по-русски.

Единый источник правды для форматов дат: используется и в моделях (__str__),
и в шаблонах (фильтры ru_date / ru_datetime), чтобы даты выглядели одинаково везде.

Спецсимвол `E` — «название месяца в родительном падеже», поэтому после числа
пишется правильно: «8 октября 2026», а не «8 Октябрь».
"""

from datetime import datetime

from django.utils import timezone
from django.utils.formats import date_format

DATE_FORMAT_RU = 'j E Y'  # 8 октября 2026
DATETIME_FORMAT_RU = 'j E Y, G:i'  # 8 октября 2026, 14:30


def _to_local(value):
    """Переводит aware-datetime в текущую зону (Europe/Moscow).

    Django-фильтр `date` делает это сам (expects_localtime=True), а
    `formats.date_format` форматирует datetime в его собственной зоне.
    Здесь выравниваем поведение, чтобы даты в моделях и шаблонах совпадали.
    """
    if isinstance(value, datetime) and timezone.is_aware(value):
        return timezone.localtime(value)
    return value


def format_date(value):
    """Дата с русским названием месяца: '8 октября 2026'."""
    if not value:
        return ''
    return date_format(_to_local(value), DATE_FORMAT_RU)


def format_datetime(value):
    """Дата и время: '8 октября 2026, 14:30'."""
    if not value:
        return ''
    return date_format(_to_local(value), DATETIME_FORMAT_RU)