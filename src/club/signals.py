"""Сигналы приложения club."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .images import compress_image, compressed_name, needs_compression
from .models import Book


@receiver(post_save, sender=Book)
def compress_book_cover(sender, instance, raw=False, **kwargs):
    """Сжимает обложку книги сразу после сохранения.

    Работает и из админки, и при программном создании книги. Повторные
    сохранения (смена названия и т.п.) обложку не трогают — см. needs_compression.
    """
    if raw or not instance.pk:
        return

    field_file = instance.cover_image
    if not needs_compression(field_file):
        return

    # Вложенный save() вызовет сигнал ещё раз — защищаемся флагом на инстансе
    if getattr(instance, '_cover_compressed', False):
        return
    instance._cover_compressed = True

    original_name = field_file.name
    with field_file.open('rb') as source:
        payload = compress_image(source)

    field_file.save(compressed_name(original_name), payload, save=False)
    instance.save(update_fields=['cover_image', 'updated_at'])

    # Исходник больше не нужен, но удаляем только если имя реально изменилось
    if original_name != field_file.name:
        sender._meta.get_field('cover_image').storage.delete(original_name)