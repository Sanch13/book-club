from django.core.management.base import BaseCommand
from django.utils import timezone
from club.models import Book, Meeting, User
from datetime import timedelta


class Command(BaseCommand):
    help = 'Инициализирует 12 книг 2026 года, админа, участников и тестовую встречу'

    def handle(self, *args, **options):
        # 1. Создание суперпользователя / админа
        admin_login = 'admin'
        if not User.objects.filter(login=admin_login).exists():
            User.objects.create_superuser(
                login=admin_login,
                email='admin@miran.local',
                password='adminpassword2026',
                role=User.Role.ADMIN,
                first_name='Администратор',
            )
            self.stdout.write(self.style.SUCCESS(f'Создан админ: {admin_login} / adminpassword2026'))
        else:
            self.stdout.write(f'Админ {admin_login} уже существует.')

        # 2. Создание тестового участника
        participant_login = 'participant1'
        if not User.objects.filter(login=participant_login).exists():
            User.objects.create_user(
                login=participant_login,
                email='user1@miran.local',
                password='password2026',
                role=User.Role.PARTICIPANT,
                first_name='Участник Клуба',
            )
            self.stdout.write(self.style.SUCCESS(f'Создан участник: {participant_login} / password2026'))

        # 3. Создание 12 книг 2026 года
        books_data = [
            (1, 'Атомарные привычки', 'Джеймс Клир', 'Как приобрести хорошие привычки и избавиться от плохих.'),
            (2, 'Дюна', 'Фрэнк Герберт', 'Эпическая фантастика на песчаной планете Арракис.'),
            (3, '451 градус по Фаренгейту', 'Рэй Брэдбери', 'Мир, в котором книги запрещены и сжигаются.'),
            (4, 'Мастер и Маргарита', 'Михаил Булгаков', 'Визит Воланда и его свиты в Москву 1930-х годов.'),
            (5, 'Шантарам', 'Грегори Дэвид Робертс', 'История беглого преступника в трущобах Бомбея.'),
            (6, 'Три товарища', 'Эрих Мария Ремарк', 'Роман о дружбе, любви и потерянном поколении.'),
            (7, 'Цветы для Элджернона', 'Дэниел Киз', 'Научный эксперимент по улучшению интеллекта.'),
            (8, 'Искусство войны', 'Сунь Цзы', 'Древний трактат о стратегии и тактике.'),
            (9, '1984', 'Джордж Оруэлл', 'Мрачная антиутопия о тоталитарном обществе.'),
            (10, 'Портрет Дориана Грея', 'Оскар Уайльд', 'Философский роман о красоте, искушении и морали.'),
            (11, 'Алхимик', 'Пауло Коэльо', 'Притча о поиске своего истинного предназначения.'),
            (12, 'Пять языков любви', 'Гэри Чепмен', 'Как выражать и принимать любовь в отношениях.'),
        ]

        for month, title, author, desc in books_data:
            book, created = Book.objects.get_or_create(
                year=2026,
                month=month,
                defaults={
                    'title': title,
                    'author': author,
                    'short_description': desc,
                    'book_page': f'https://example.com/books/{month}-2026',
                }
            )
            if created:
                self.stdout.write(f'Создана книга (Месяц {month}): {title}')
            else:
                self.stdout.write(f'Книга за месяц {month} уже существует.')

        # 4. Создание встречи
        if not Meeting.objects.exists():
            Meeting.objects.create(
                title='Первая встреча Книжного клуба 2026',
                date_time=timezone.now() + timedelta(days=15),
                location='Конференц-зал №1 / Онлайн (Zoom)',
                description='Обсуждаем книгу января: "Атомарные привычки" Джеймса Клира.',
            )
            self.stdout.write(self.style.SUCCESS('Создана тестовая встреча книжного клуба.'))

        self.stdout.write(self.style.SUCCESS('Инициализация успешно завершена!'))
