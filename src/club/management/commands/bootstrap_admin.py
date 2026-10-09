"""Создать администратора в пустой базе.

Зачем отдельная команда, если есть createsuperuser: логин проверяет белый
список, а createsuperuser про него ничего не знает. Пользователь был бы
создан, но на /admin/ не пустил бы — ни его, ни новых участников.

Команда делает обе части в одной транзакции: суперпользователь и запись
в белом списке с его адресом. Запуск повторно на существующем адресе
ничего не ломает и не перетирает пароль.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from club.models import Book
from user.models import User, WhitelistEmail, normalize_email


class Command(BaseCommand):
    help = 'Создать администратора и внести его email в белый список.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True, help='Email администратора.')
        parser.add_argument('--password', required=True, help='Пароль администратора.')

    def handle(self, *args, **options):
        email = normalize_email(options['email'])
        password = options['password']

        if not email or '@' not in email:
            raise CommandError(f'Некорректный email: {email!r}')
        if len(password) < 8:
            raise CommandError('Пароль короче 8 символов.')

        with transaction.atomic():
            user = User.objects.filter(email__iexact=email).first()
            if user is None:
                user = User.objects.create_superuser(email=email, password=password)
                self.stdout.write(self.style.SUCCESS(f'Создан администратор {email}'))
            else:
                # Уже существует — доукомплектовываем, а не пересоздаём:
                # иначе пароль сбросился бы при повторном запуске.
                changed = []
                if not user.is_staff:
                    user.is_staff = True
                    changed.append('is_staff')
                if not user.is_superuser:
                    user.is_superuser = True
                    changed.append('is_superuser')
                if user.role != User.Role.ADMIN:
                    user.role = User.Role.ADMIN
                    changed.append('role')
                if not user.is_active:
                    user.is_active = True
                    changed.append('is_active')
                if changed:
                    user.save(update_fields=changed)
                self.stdout.write(f'Администратор {email} уже был, обновлено: {changed or "ничего"}')

            _, created = WhitelistEmail.objects.get_or_create(
                email=email, defaults={'comment': 'Администратор (создан командой)'}
            )
            verb = 'добавлен' if created else 'уже был'
            self.stdout.write(f'Белый список: {email} {verb}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Готово. Вход: /admin/ и /login/ по этому email.'))
        self.stdout.write('')
        if Book.objects.exists():
            self.stdout.write(f'Книг в базе: {Book.objects.count()}')
        else:
            self.stdout.write(
                self.style.WARNING(
                    'Книг в базе нет — программу года нужно заполнить через админку '
                    'или командой init_2025_books.'
                )
            )
