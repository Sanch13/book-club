from django.conf import settings
from django.db import models
from django.db.models import Avg


class Book(models.Model):
    year = models.PositiveIntegerField('Год', default=2026)
    month = models.PositiveIntegerField('Месяц (1-12)', default=1)
    title = models.CharField('Название книги', max_length=255)
    author = models.CharField('Автор', max_length=255)
    short_description = models.TextField('Краткое описание')
    cover_image = models.ImageField(
        'Обложка', upload_to='books/covers/', blank=True, null=True
    )
    book_page = models.CharField(
        'Страница книги (URL или текст)', max_length=500, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['month']
        verbose_name = 'Книга'
        verbose_name_plural = 'Книги'

    def __str__(self):
        return f'{self.month}. {self.title} — {self.author}'

    @property
    def average_rating(self):
        avg = self.votes.aggregate(Avg('rating'))['rating__avg']
        return round(avg, 1) if avg is not None else None


class BookAttachment(models.Model):
    class AttachmentType(models.TextChoices):
        PDF = 'pdf', 'PDF'
        PPT = 'ppt', 'PPT'

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
    file = models.FileField('Файл', upload_to='books/attachments/')
    title = models.CharField(
        'Заголовок материала', max_length=255, blank=True, default='Материалы'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Материал книги'
        verbose_name_plural = 'Материалы книг'

    def __str__(self):
        return f'{self.get_file_type_display()} - {self.title} ({self.book.title})'


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
        return f'{self.title} ({self.date_time.strftime("%d.%m.%Y %H:%M")})'
