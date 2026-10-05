import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Book',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('year', models.PositiveIntegerField(default=2026, verbose_name='Год')),
                ('month', models.PositiveIntegerField(default=1, verbose_name='Месяц (1-12)')),
                ('title', models.CharField(max_length=255, verbose_name='Название книги')),
                ('author', models.CharField(max_length=255, verbose_name='Автор')),
                ('short_description', models.TextField(verbose_name='Краткое описание')),
                ('cover_image', models.ImageField(blank=True, null=True, upload_to='books/covers/', verbose_name='Обложка')),
                ('book_page', models.CharField(blank=True, max_length=500, verbose_name='Страница книги (URL или текст)')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Книга',
                'verbose_name_plural': 'Книги',
                'ordering': ['month'],
            },
        ),
        migrations.CreateModel(
            name='Meeting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(default='Встреча книжного клуба', max_length=255, verbose_name='Название встречи')),
                ('date_time', models.DateTimeField(verbose_name='Дата и время')),
                ('location', models.CharField(max_length=255, verbose_name='Место проведения / Ссылка')),
                ('description', models.TextField(blank=True, verbose_name='Описание')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Встреча',
                'verbose_name_plural': 'Встречи',
                'ordering': ['date_time'],
            },
        ),
        migrations.CreateModel(
            name='Vote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rating', models.PositiveIntegerField(choices=[(1, '1'), (2, '2'), (3, '3'), (4, '4'), (5, '5'), (6, '6'), (7, '7'), (8, '8'), (9, '9'), (10, '10')], verbose_name='Балл (1-10)')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('book', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='votes', to='club.book', verbose_name='Книга')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='votes', to=settings.AUTH_USER_MODEL, verbose_name='Участник')),
            ],
            options={
                'verbose_name': 'Голос',
                'verbose_name_plural': 'Голоса',
                'unique_together': {('book', 'user')},
            },
        ),
        migrations.CreateModel(
            name='BookAttachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file_type', models.CharField(choices=[('pdf', 'PDF'), ('ppt', 'PPT')], default='pdf', max_length=10, verbose_name='Тип файла')),
                ('file', models.FileField(upload_to='books/attachments/', verbose_name='Файл')),
                ('title', models.CharField(blank=True, default='Материалы', max_length=255, verbose_name='Заголовок материала')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('book', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='club.book', verbose_name='Книга')),
            ],
            options={
                'verbose_name': 'Материал книги',
                'verbose_name_plural': 'Материалы книг',
            },
        ),
        migrations.CreateModel(
            name='Review',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.TextField(verbose_name='Текст отзыва')),
                ('created_at', models.DateTimeField('Создан', auto_now_add=True)),
                ('updated_at', models.DateTimeField('Обновлен', auto_now=True)),
                ('book', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reviews', to='club.book', verbose_name='Книга')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reviews', to=settings.AUTH_USER_MODEL, verbose_name='Автор')),
            ],
            options={
                'verbose_name': 'Отзыв',
                'verbose_name_plural': 'Отзывы',
                'ordering': ['-created_at'],
            },
        ),
    ]