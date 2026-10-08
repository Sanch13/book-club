from django.core.management.base import BaseCommand

from club.models import Book, Review, Vote
from user.models import User, WhitelistEmail

PASSWORD = 'password2025'

# Тестовые участники: без них нельзя создать голоса и отзывы
PARTICIPANTS = [
    ('reader1@miran.local', 'Читатель 1'),
    ('reader2@miran.local', 'Читатель 2'),
    ('reader3@miran.local', 'Читатель 3'),
]

# (месяц, название, автор, описание, оценки, отзыв)
# Оценки соответствуют PARTICIPANTS по порядку: [reader1, reader2, reader3].
BOOKS_DATA = [
    (
        1, 'Сто лет одиночества', 'Габриэль Гарсиа Маркес',
        'История семьи Буэндио на протяжении семи поколений.',
        [9, 8, 9], 'Перечитывал трижды. Язык невероятный, но дается тяжело.',
    ),
    (
        2, 'Мы', 'Евгений Замятин',
        'Антиутопия о строительстве бесконечного Собора и радости.',
        [7, 8, 6], 'Короткая, но очень цепляющая. Перечитываю каждый год.',
    ),
    (
        3, 'Процесс', 'Франц Кафка',
        'Человек, которого приводит суд, не называя вины.',
        [8, 7, 8], 'Привычная классика, но именно этот перевод зашёл лучше.',
    ),
    (
        4, 'Три сестры', 'Антон Чехов',
        'Три сестры и их попытки найти собственный смысл жизни.',
        [7, 7, 8], 'Тихая, грустная и очень точная книга.',
    ),
    (
        5, 'Соблазн святого Антония', 'Ги Флукбер',
        'Отшельник умирает, а искушение находит для него другую форму.',
        [9, 9, 8], 'Лучшее, что читал в этом году. Читается за один вечер.',
    ),
    (
        6, 'Смерть Ивана Ильича', 'Лев Толстой',
        'Обычная жизнь чиновника, которая заканчивается неожиданно.',
        [8, 9, 9], 'Перечитываю каждый раз. Ничего лишнего, всё работает.',
    ),
    (
        7, 'Волшебная гора', 'Томас Манн',
        'Молодой человек приезжает в санаторий и попадает в особый мир.',
        [6, 7, 6], 'Читал долго и неравномерно, но образ Андрея запомнился.',
    ),
    (
        8, 'Малый Принц', 'Антуан де Сент-Экзюпери',
        'Маленький путешественник с астероида задает взрослым вопросы.',
        [9, 8, 9], 'Идеально, чтобы подарить кому-то под Новый год.',
    ),
    (
        9, 'Земля', 'Анатолий Рыбаков',
        'Хроника одной коммунальной квартиры в сталинском СССР.',
        [8, 8, 7], 'Точное и очень узнаваемое описание эпохи.',
    ),
    (
        10, 'Дети Ванюшина', 'Андрей Бунин',
        'Рассказы о детстве, которые читаются как воспоминания.',
        [7, 6, 7], 'Тонкая проза. Отдельные рассказы сильнее всего сборника.',
    ),
    (
        11, 'Пикник на обочине', 'Аркадий и Борис Стругацкие',
        'Странники охотятся за артефактами среди руин после катастрофы.',
        [8, 7, 9], 'Читается на одном дыхании, несмотря на объем.',
    ),
    (
        12, 'Лолита', 'Владимир Набоков',
        'Рассказ убийцы о своей связи с двенадцатилетней девочкой.',
        [5, 4, 6], 'Мастерство языка безупречное, но читать тяжело.',
    ),
]


class Command(BaseCommand):
    help = 'Инициализирует 12 книг 2025 года с голосами и отзывами (тестовые данные)'

    def handle(self, *args, **options):
        # 1. Тестовые участники (нужны для голосов и отзывов)
        users = []
        for email, name in PARTICIPANTS:
            _, created = WhitelistEmail.objects.get_or_create(
                email=email, defaults={'comment': name}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Email добавлен в белый список: {email}'))

            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'role': User.Role.PARTICIPANT,
                    'first_name': name,
                },
            )
            if created:
                user.set_password(PASSWORD)
                user.save()
                self.stdout.write(
                    self.style.SUCCESS(f'Создан участник: {email} / {PASSWORD}')
                )
            else:
                self.stdout.write(f'Участник {email} уже существует.')
            users.append(user)

        # 2. Книги 2025 года с голосами и отзывами
        for month, title, author, desc, ratings, review_text in BOOKS_DATA:
            book, created = Book.objects.get_or_create(
                year=2025,
                month=month,
                defaults={
                    'title': title,
                    'author': author,
                    'short_description': desc,
                },
            )
            if created:
                self.stdout.write(f'Создана книга ({book.month_name}): {title}')
            else:
                self.stdout.write(f'Книга за месяц {book.month_name} уже существует.')

            # Голоса: список оценок по порядку соответствует участникам
            for user, rating in zip(users, ratings):
                _, vote_created = Vote.objects.get_or_create(
                    book=book,
                    user=user,
                    defaults={'rating': rating},
                )
                if vote_created:
                    self.stdout.write(f'  голос: {user.email} -> {rating}')

            # Отзыв от первого участника
            _, review_created = Review.objects.get_or_create(
                book=book,
                user=users[0],
                text=review_text,
            )
            if review_created:
                self.stdout.write(f'  отзыв: {users[0].email}')

        # 3. Сводка
        self.stdout.write(self.style.SUCCESS('\nИнициализация 2025 года успешно завершена!'))
        self.stdout.write(
            f'Книг за 2025: {Book.objects.filter(year=2025).count()}, '
            f'голосов: {Vote.objects.filter(book__year=2025).count()}, '
            f'отзывов: {Review.objects.filter(book__year=2025).count()}'
        )