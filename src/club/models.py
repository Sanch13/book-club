from django.conf import settings
from django.db import models
from django.db.models import Avg

from .dateutils import format_datetime

MONTH_CHOICES = [
    (1, 'Январь'),
    (2, 'Февраль'),
    (3, 'Март'),
    (4, 'Апрель'),
    (5, 'Май'),
    (6, 'Июнь'),
    (7, 'Июль'),
    (8, 'Август'),
    (9, 'Сентябрь'),
    (10, 'Октябрь'),
    (11, 'Ноябрь'),
    (12, 'Декабрь'),
]


class Book(models.Model):
    year = models.PositiveIntegerField('Год', default=2026)
    month = models.PositiveIntegerField('Месяц', choices=MONTH_CHOICES, default=1)
    title = models.CharField('Название книги', max_length=255)
    author = models.CharField('Автор', max_length=255)
    short_description = models.TextField('Краткое описание')
    cover_image = models.ImageField(
        'Обложка', upload_to='books/covers/', blank=True, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['month']
        verbose_name = 'Книга'
        verbose_name_plural = 'Книги'

    def __str__(self):
        return f'{self.month_name}: {self.title} — {self.author}'

    @property
    def month_name(self):
        """Название месяца по-русски (напр. 1 -> 'Январь')."""
        return self.get_month_display()

    @property
    def average_rating(self):
        avg = self.votes.aggregate(Avg('rating'))['rating__avg']
        return round(avg, 1) if avg is not None else None


class BookAttachment(models.Model):
    class AttachmentType(models.TextChoices):
        # Только форматы, которые браузер открывает сам. PPT/PDF-документы
        # Office браузер не отображает — только скачивает, поэтому их нет.
        PDF = 'pdf', 'PDF'
        MP3 = 'mp3', 'MP3'
        MP4 = 'mp4', 'MP4'

    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name='attachments',
        verbose_name='Книга',
    )
    file_type = models.CharField(
        'Тип файла',
        max_length=10,
        choices=AttachmentType.choices,
        default=AttachmentType.PDF,
    )
    # blank=True: строка может существовать без файла — тогда на странице
    # книги вместо ссылки показывается серая заглушка.
    file = models.FileField('Файл', upload_to='books/attachments/', blank=True)
    title = models.CharField('Название', max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['file_type', 'created_at']
        verbose_name = 'Файл книги'
        verbose_name_plural = 'Файлы книг'

    def __str__(self):
        return f'{self.get_file_type_display()} - {self.display_name} ({self.book.title})'

    @property
    def file_name(self):
        """Имя загруженного файла без пути и расширения-дубля."""
        if not self.file:
            return ''
        return self.file.name.rsplit('/', 1)[-1]

    @property
    def display_name(self):
        """Что показывать пользователю: заданное название или имя файла."""
        return self.title or self.file_name

    @property
    def has_file(self):
        """Есть ли реально доступный файл (а не только запись в БД)."""
        return bool(self.file) and self.file.storage.exists(self.file.name)

    @property
    def file_url(self):
        return self.file.url if self.has_file else ''


class Vote(models.Model):
    book = models.ForeignKey(
        Book, on_delete=models.CASCADE, related_name='votes', verbose_name='Книга'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='votes',
        verbose_name='Участник',
    )
    rating = models.PositiveIntegerField(
        'Балл (1-10)', choices=[(i, str(i)) for i in range(1, 11)]
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('book', 'user')
        verbose_name = 'Голос'
        verbose_name_plural = 'Голоса'

    def __str__(self):
        return f'{self.user.email} -> {self.book.title}: {self.rating}'


class Favorite(models.Model):
    """Самая любимая книга участника — ровно одна за всё время.

    OneToOne, а не обычный ForeignKey: «одна на пользователя» тогда
    обеспечивает сама БД, и нельзя случайно сохранить два сердечка
    подряд при гонке двух запросов. Снять выбор с одной книги и поставить
    на другую — это один UPDATE той же строки, а не удаление плюс вставка.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='favorite',
        verbose_name='Участник',
    )
    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name='favorited_by',
        verbose_name='Книга',
    )
    created_at = models.DateTimeField('Отмечено', auto_now_add=True)

    class Meta:
        verbose_name = 'Любимая книга'
        verbose_name_plural = 'Любимые книги'

    def __str__(self):
        return f'{self.user.display_name} → {self.book.title}'


class Review(models.Model):
    book = models.ForeignKey(
        Book, on_delete=models.CASCADE, related_name='reviews', verbose_name='Книга'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews',
        verbose_name='Автор',
    )
    text = models.TextField('Текст отзыва')
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлен', auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Отзыв'
        verbose_name_plural = 'Отзывы'

    def __str__(self):
        return f'Отзыв от {self.user.email} на {self.book.title}'


class ReviewComment(models.Model):
    review = models.ForeignKey(
        Review, on_delete=models.CASCADE, related_name='comments', verbose_name='Отзыв'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='review_comments',
        verbose_name='Автор',
    )
    text = models.TextField('Текст комментария')
    created_at = models.DateTimeField('Создан', auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Комментарий'
        verbose_name_plural = 'Комментарии'

    def __str__(self):
        return f'Комментарий от {self.user.email} к отзыву #{self.review_id}'


class Meeting(models.Model):
    title = models.CharField(
        'Название встречи', max_length=255, default='Встреча книжного клуба'
    )
    date_time = models.DateTimeField('Дата и время')
    location = models.CharField('Место проведения / Ссылка', max_length=255)
    description = models.TextField('Описание', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['date_time']
        verbose_name = 'Встреча'
        verbose_name_plural = 'Встречи'

    def __str__(self):
        return f'{self.title} ({format_datetime(self.date_time)})'
