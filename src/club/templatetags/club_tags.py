from django import template

from club.dateutils import format_date, format_datetime
from club.models import Vote

register = template.Library()

@register.filter(name='dict_key')
def dict_key(d, key):
    if d is None:
        return None
    return d.get(key)


@register.simple_tag
def rating_scale():
    """Шкала оценок (1-10) — берётся из choices поля Vote.rating.

    Единый источник правды: в шаблоне нельзя случайно «размножить» шкалу,
    как это было с {% for i in "12345678910"|make_list %} (11 кнопок).
    """
    return Vote._meta.get_field('rating').choices


@register.filter(name='ru_date')
def ru_date(value):
    """Дата по-русски: 8 октября 2026."""
    return format_date(value)


@register.filter(name='ru_datetime')
def ru_datetime(value):
    """Дата и время по-русски: 8 октября 2026, 14:30."""
    return format_datetime(value)
