import re
from datetime import datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.utils import IntegrityError
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from club.dateutils import format_date, format_datetime
from club.models import (
    MONTH_CHOICES,
    Book,
    BookAttachment,
    Favorite,
    Meeting,
    Review,
    ReviewComment,
    Vote,
)
from club.templatetags.club_tags import rating_scale, ru_plural
from user.models import User, WhitelistEmail, normalize_email

MSK = ZoneInfo('Europe/Moscow')


def moscow(year, month, day, hour=0, minute=0):
    """datetime с явной зоной Europe/Moscow (timezone.TIME_ZONE проекта)."""
    return datetime(year, month, day, hour, minute, tzinfo=MSK)


@pytest.mark.django_db
class TestBookClub:
    def test_book_average_rating(self):
        book = Book.objects.create(
            month=1,
            title='Тестовая книга',
            author='Тестовый автор',
            short_description='Описание'
        )
        assert book.average_rating is None

        user1 = User.objects.create_user(email='user1@miran.local', password='password')
        user2 = User.objects.create_user(email='user2@miran.local', password='password')

        Vote.objects.create(book=book, user=user1, rating=8)
        Vote.objects.create(book=book, user=user2, rating=10)

        # Average of 8 and 10 is 9.0
        assert book.average_rating == 9.0

    def test_review_permissions(self, client):
        user1 = User.objects.create_user(email='author1@miran.local', password='password')
        user2 = User.objects.create_user(email='author2@miran.local', password='password')
        book = Book.objects.create(
            month=2,
            title='Книга отзывов',
            author='Автор',
            short_description='Описание'
        )

        review = Review.objects.create(book=book, user=user1, text='Первый отзыв')

        # Log in as user2 (not author)
        client.force_login(user2)
        response = client.get(reverse('edit_review', args=[review.pk]))
        assert response.status_code == 403

        # Log in as user1 (author)
        client.force_login(user1)
        response = client.get(reverse('edit_review', args=[review.pk]))
        assert response.status_code == 200

        # Edit review
        response = client.post(reverse('edit_review', args=[review.pk]), {'text': 'Обновленный отзыв'})
        assert response.status_code == 302
        review.refresh_from_db()
        assert review.text == 'Обновленный отзыв'

    def test_voting_view(self, client):
        user = User.objects.create_user(email='voter1@miran.local', password='password')
        book = Book.objects.create(
            month=3,
            title='Книга голосования',
            author='Автор',
            short_description='Описание'
        )

        client.force_login(user)
        response = client.post(reverse('book_detail', args=[book.pk]), {'vote_rating': '9'})
        assert response.status_code == 302

        vote = Vote.objects.get(book=book, user=user)
        assert vote.rating == 9

        # Update vote
        client.post(reverse('book_detail', args=[book.pk]), {'vote_rating': '5'})
        vote.refresh_from_db()
        assert vote.rating == 5
        assert Vote.objects.filter(book=book, user=user).count() == 1

    def test_rating_scale_is_exactly_1_to_10(self):
        scale = list(rating_scale())
        assert [value for value, _ in scale] == list(range(1, 11))

    def test_book_detail_renders_exactly_10_vote_buttons(self, client):
        """Регрессия: шкала не должна содержать 11-ю кнопку.

        Раньше в шаблоне стояло {% for i in "12345678910"|make_list %} —
        строка из 11 символов, поэтому рендерилось 11 кнопок (1-11).
        """
        user = User.objects.create_user(email='scale@miran.local', password='password')
        book = Book.objects.create(
            month=4,
            title='Книга шкалы',
            author='Автор',
            short_description='Описание'
        )

        client.force_login(user)
        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()

        values = re.findall(r'name="vote_rating" value="(\d+)"', html)
        assert values == [str(i) for i in range(1, 11)]
        assert 'value="11"' not in html

    def test_vote_rejected_above_scale(self, client):
        """Балл вне шкалы 1-10 не должен сохраняться."""
        user = User.objects.create_user(email='overflow@miran.local', password='password')
        book = Book.objects.create(
            month=5,
            title='Книга переполнения',
            author='Автор',
            short_description='Описание'
        )

        client.force_login(user)
        client.post(reverse('book_detail', args=[book.pk]), {'vote_rating': '11'})
        assert not Vote.objects.filter(book=book, user=user).exists()


@pytest.mark.django_db
class TestBookMonth:
    def test_month_choices_cover_all_twelve_months(self):
        assert [value for value, _ in MONTH_CHOICES] == list(range(1, 13))

    def test_month_choices_are_russian_names(self):
        names = dict(MONTH_CHOICES)
        assert names[1] == 'Январь'
        assert names[2] == 'Февраль'
        assert names[12] == 'Декабрь'

    @pytest.mark.parametrize('month, expected', list(MONTH_CHOICES))
    def test_month_name_property(self, month, expected):
        book = Book.objects.create(
            month=month,
            title='Книга',
            author='Автор',
            short_description='Описание'
        )
        assert book.month_name == expected

    def test_book_str_uses_month_name(self):
        book = Book.objects.create(
            month=2,
            title='Дюна',
            author='Фрэнк Герберт',
            short_description='Описание'
        )
        assert str(book) == 'Февраль: Дюна — Фрэнк Герберт'
        assert '2' not in str(book).split(':')[0]

    def test_templates_render_month_name_not_number(self, client):
        """Месяц должен показываться названием, а не числом."""
        user = User.objects.create_user(email='month@miran.local', password='password')
        book = Book.objects.create(
            month=11,
            title='Алхимик',
            author='Пауло Коэльо',
            short_description='Описание'
        )
        client.force_login(user)
        # На главной показывается только топ-3 книг по рейтингу, поэтому нужен голос
        Vote.objects.create(book=book, user=user, rating=9)

        detail = client.get(reverse('book_detail', args=[book.pk])).content.decode()
        assert 'Ноябрь' in detail
        assert 'Месяц 11' not in detail

        book_list = client.get(reverse('book_list')).content.decode()
        assert 'Ноябрь' in book_list
        assert 'Месяц 11' not in book_list

        index = client.get(reverse('index')).content.decode()
        assert 'Ноябрь' in index
        assert 'Месяц 11' not in index


@pytest.mark.django_db
class TestRussianDates:
    def test_format_date_uses_russian_month_name_lowercase(self):
        assert format_date(moscow(2026, 10, 8, 14, 30)) == '8 октября 2026'

    def test_format_datetime_uses_russian_month_name_lowercase(self):
        assert format_datetime(moscow(2026, 10, 8, 14, 30)) == '8 октября 2026, 14:30'

    def test_month_name_is_not_capitalized_after_number(self):
        """По-русски после числа месяц со строчной буквы ('8 октября')."""
        for month in range(1, 13):
            rendered = format_date(moscow(2026, month, 1, 12, 0))
            month_word = rendered.split()[1]
            assert month_word[0].islower(), rendered

    def test_format_handles_none(self):
        assert format_date(None) == ''
        assert format_datetime(None) == ''

    def test_datetime_rendered_in_project_timezone(self):
        """UTC из БД должен показываться в московском времени (+03:00)."""
        utc_value = moscow(2026, 10, 8, 14, 30).astimezone(ZoneInfo('UTC'))
        assert format_datetime(utc_value) == '8 октября 2026, 14:30'

    def test_meeting_str_uses_russian_date(self):
        meeting = Meeting.objects.create(
            title='Встреча клуба',
            date_time=moscow(2026, 10, 8, 14, 30),
            location='Zoom'
        )
        assert str(meeting) == 'Встреча клуба (8 октября 2026, 14:30)'

    def test_templates_render_russian_dates(self, client):
        user = User.objects.create_user(email='dates@miran.local', password='password')
        # Дата в будущем: главная показывает только предстоящие встречи,
        # поэтому фиксированная дата «протухала» бы на следующий день.
        when = (timezone.localtime() + timedelta(days=3)).replace(
            hour=14, minute=30, second=0, microsecond=0
        )
        expected = format_datetime(when)

        book = Book.objects.create(
            month=10,
            title='Книга',
            author='Автор',
            short_description='Описание'
        )
        review = Review.objects.create(book=book, user=user, text='Отзыв')
        # created_at — auto_now_add, поэтому задаётся только через UPDATE
        Review.objects.filter(pk=review.pk).update(created_at=when)
        Meeting.objects.create(
            title='Встреча',
            date_time=when,
            location='Zoom'
        )
        client.force_login(user)

        detail = client.get(reverse('book_detail', args=[book.pk])).content.decode()
        assert expected in detail

        index = client.get(reverse('index')).content.decode()
        assert expected in index

    def test_book_detail_badge_uses_book_year(self, client):
        """Год в бейдже берётся из модели, а не захардкожен."""
        user = User.objects.create_user(email='year@miran.local', password='password')
        book = Book.objects.create(
            year=2026,
            month=1,
            title='Книга',
            author='Автор',
            short_description='Описание'
        )
        client.force_login(user)
        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()
        assert '• 2026</span>' in html


@pytest.mark.django_db
class TestReviewComments:
    @pytest.fixture
    def book(self):
        return Book.objects.create(
            month=6,
            title='Книга с комментариями',
            author='Автор',
            short_description='Описание'
        )

    def test_user_can_comment_other_users_review(self, client, book):
        author = User.objects.create_user(email='reviewer@miran.local', password='password')
        commenter = User.objects.create_user(email='commenter@miran.local', password='password')
        review = Review.objects.create(book=book, user=author, text='Мой отзыв')

        client.force_login(commenter)
        response = client.post(
            reverse('add_review_comment', args=[review.pk]),
            {'text': 'Не согласен с выводом'},
        )

        assert response.status_code == 302
        comment = ReviewComment.objects.get(review=review)
        assert comment.text == 'Не согласен с выводом'
        assert comment.user == commenter

    def test_comment_appears_on_book_page(self, client, book):
        author = User.objects.create_user(email='reviewer2@miran.local', password='password')
        commenter = User.objects.create_user(email='commenter2@miran.local', password='password')
        review = Review.objects.create(book=book, user=author, text='Отзыв для проверки')
        ReviewComment.objects.create(
            review=review,
            user=commenter,
            text='Согласен, отличная книга',
        )

        client.force_login(commenter)
        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()
        assert 'Согласен, отличная книга' in html
        assert 'commenter2@miran.local' in html

    def test_comment_form_rendered_for_every_review(self, client, book):
        """Форма комментария обязана рендериться под каждым отзывом.

        Если бы dict_key не нашёл форму, шаблон отрисовал бы пустоту
        без ошибки — поэтому проверяем action и textarea явно.
        """
        user = User.objects.create_user(email='forms@miran.local', password='password')
        review1 = Review.objects.create(book=book, user=user, text='Первый отзыв')
        review2 = Review.objects.create(book=book, user=user, text='Второй отзыв')

        client.force_login(user)
        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()

        for review in (review1, review2):
            expected_url = reverse('add_review_comment', args=[review.pk])
            assert f'action="{expected_url}"' in html
        # по одному textarea комментария на каждый отзыв
        comment_textareas = re.findall(r'Напишите комментарий к отзыву', html)
        assert len(comment_textareas) == 2

    @pytest.mark.parametrize(('n', 'word'), [
        (0, 'книг'), (1, 'книга'), (2, 'книги'), (4, 'книги'), (5, 'книг'),
        (11, 'книг'), (12, 'книг'), (14, 'книг'), (21, 'книга'), (22, 'книги'),
        (25, 'книг'), (101, 'книга'), (111, 'книг'), (1000, 'книг'),
    ])
    def test_ru_plural_forms(self, n, word):
        assert ru_plural(n, 'книга,книги,книг') == word

    def test_ru_plural_tolerates_garbage(self):
        """Битое значение не должно ронять страницу — отдаём форму множественного числа."""
        assert ru_plural(None, 'книга,книги,книг') == 'книг'
        assert ru_plural('abc', 'книга,книги,книг') == 'книг'

    def test_comments_of_other_review_not_shown(self, client, book):
        """Комментарии не должны протекать между отзывами одной книги."""
        user = User.objects.create_user(email='isolation@miran.local', password='password')
        review1 = Review.objects.create(book=book, user=user, text='Отзыв один')
        review2 = Review.objects.create(book=book, user=user, text='Отзыв два')
        ReviewComment.objects.create(review=review1, user=user, text='комментарий к первому')

        client.force_login(user)
        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()
        assert 'комментарий к первому' in html
        # комментарий привязан к review1, а не ко всей книге
        assert review1.comments.count() == 1
        assert review2.comments.count() == 0

    def test_can_comment_own_review(self, client, book):
        user = User.objects.create_user(email='selfcomment@miran.local', password='password')
        review = Review.objects.create(book=book, user=user, text='Свой отзыв')

        client.force_login(user)
        client.post(
            reverse('add_review_comment', args=[review.pk]),
            {'text': 'Уточнение к моему отзыву'},
        )

        assert ReviewComment.objects.filter(
            review=review,
            text='Уточнение к моему отзыву'
        ).exists()

    def test_empty_comment_rejected(self, client, book):
        user = User.objects.create_user(email='empty@miran.local', password='password')
        review = Review.objects.create(book=book, user=user, text='Отзыв')

        client.force_login(user)
        response = client.post(
            reverse('add_review_comment', args=[review.pk]),
            {'text': '   '},
        )

        assert response.status_code == 302
        assert not ReviewComment.objects.exists()

    def test_comments_ordered_newest_first(self, client, book):
        user = User.objects.create_user(email='order@miran.local', password='password')
        review = Review.objects.create(book=book, user=user, text='Отзыв')

        ReviewComment.objects.create(review=review, user=user, text='первый')
        ReviewComment.objects.create(review=review, user=user, text='второй')
        ReviewComment.objects.create(review=review, user=user, text='третий')

        comments = list(review.comments.all())
        assert [c.text for c in comments] == ['третий', 'второй', 'первый']

    def test_comment_requires_login(self, client, book):
        user = User.objects.create_user(email='anon@miran.local', password='password')
        review = Review.objects.create(book=book, user=user, text='Отзыв')

        response = client.post(
            reverse('add_review_comment', args=[review.pk]),
            {'text': 'анонимный комментарий'},
        )

        assert response.status_code == 302
        assert '/login/' in response.url
        assert not ReviewComment.objects.exists()

    def test_comment_to_missing_review_returns_404(self, client):
        user = User.objects.create_user(email='nobody@miran.local', password='password')
        client.force_login(user)
        response = client.post(
            reverse('add_review_comment', args=[99999]),
            {'text': 'комментарий в никуда'},
        )
        assert response.status_code == 404
        assert not ReviewComment.objects.exists()

    def test_comments_deleted_with_review(self, book):
        """Каскад: комментарии удаляются вместе с отзывом."""
        user = User.objects.create_user(email='cascade@miran.local', password='password')
        review = Review.objects.create(book=book, user=user, text='Отзыв')
        ReviewComment.objects.create(review=review, user=user, text='Комментарий')

        review.delete()
        assert not ReviewComment.objects.exists()


@pytest.mark.django_db
class TestHeaderLogo:
    def test_header_shows_logo_instead_of_miran_badge(self, client):
        user = User.objects.create_user(email='logo@miran.local', password='password')
        book = Book.objects.create(
            month=3, title='Книга', author='Автор', short_description='Описание'
        )

        client.force_login(user)
        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()

        assert 'images/logo.png' in html
        assert '>MIRAN<' not in html

    def test_logo_url_is_absolute(self, client):
        """Относительный src сломался бы на вложенных URL (/books/1/)."""
        user = User.objects.create_user(email='logo2@miran.local', password='password')
        book = Book.objects.create(
            month=4, title='Книга', author='Автор', short_description='Описание'
        )
        client.force_login(user)

        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()
        src = re.search(r'<img[^>]*src="([^"]*logo\.png)"', html).group(1)
        assert src.startswith('/static/')

    def test_logo_file_exists(self):
        from django.conf import settings

        path = settings.BASE_DIR / 'static' / 'images' / 'logo.png'
        assert path.exists(), 'Логотип не найден в static/images/logo.png'
        assert path.stat().st_size > 0

    def test_logo_has_transparent_background(self):
        """Непрозрачный фон дал бы белую рамку на серой шапке."""
        from django.conf import settings
        from PIL import Image

        path = settings.BASE_DIR / 'static' / 'images' / 'logo.png'
        image = Image.open(path).convert('RGBA')
        alpha = image.getchannel('A')
        assert alpha.getextrema()[0] == 0, 'У логотипа нет прозрачного фона'


@pytest.mark.django_db
class TestHeaderYearMenu:
    """Выпадающий список годов в шапке: активный пункт и галочка."""

    @pytest.fixture
    def user(self):
        return User.objects.create_user(email='menu@miran.local', password='p')

    @pytest.fixture
    def books(self):
        year = timezone.now().year
        return [
            Book.objects.create(year=year, month=1, title='Эта', author='А',
                                short_description='D'),
            Book.objects.create(year=year - 1, month=1, title='Прошлая', author='А',
                                short_description='D'),
        ]

    def _marked_year(self, html):
        """Какой год отмечен в шапке.

        Возвращает строку года, 'all' для пункта «Все годы»
        или None, если не отмечен никто.
        """
        nav = re.search(r'<nav class="hidden md:flex.*?</nav>', html, re.DOTALL)
        assert nav, 'В шапке нет навигации'

        # aria-current="page" есть только у отмеченного пункта года, поэтому
        # искать его прямо в навигации можно — вырезать выпадающий список
        # не нужно (внутри есть <div>разделитель, который обрывает вложенность)
        for tag in re.findall(
            r'<a href="[^"]*"[^>]*aria-current="page"[^>]*>.*?</a>',
            nav.group(0),
            re.DOTALL,
        ):
            if 'Все годы' in tag:
                return 'all'
            year = re.search(r'(\d{4})', tag)
            if year:
                return year.group(1)
        return None

    def test_index_marks_current_year(self, client, user, books):
        """На главной галочка стоит на текущем календарном году."""
        client.force_login(user)
        html = client.get(reverse('index')).content.decode()

        assert self._marked_year(html) == str(timezone.now().year)
        assert 'aria-current="page"' in html

    def test_index_falls_back_to_latest_year_with_books(self, client, user, books):
        """Если книг за текущий год нет, отмечается год, где они есть."""
        Book.objects.filter(year=timezone.now().year).delete()

        client.force_login(user)
        html = client.get(reverse('index')).content.decode()
        assert self._marked_year(html) == str(timezone.now().year - 1)

    def test_book_list_marks_its_year(self, client, user, books):
        client.force_login(user)
        html = client.get(
            reverse('book_list_year', args=[timezone.now().year - 1])
        ).content.decode()

        assert self._marked_year(html) == str(timezone.now().year - 1)

    def test_all_years_page_marks_all_years(self, client, user, books):
        client.force_login(user)
        response = client.get(reverse('book_list'))

        assert response.context['all_years'] is True
        html = response.content.decode()
        # отмечен именно «Все годы», а не какой-то конкретный год
        assert self._marked_year(html) == 'all'

    def test_book_detail_marks_current_year(self, client, user, books):
        """На странице книги год не задан вьюхом — пункт всё равно выбран."""
        client.force_login(user)
        html = client.get(reverse('book_detail', args=[books[0].pk])).content.decode()

        assert self._marked_year(html) == str(timezone.now().year)

    def test_profile_marks_current_year(self, client, user, books):
        client.force_login(user)
        html = client.get(reverse('profile')).content.decode()
        assert self._marked_year(html) == str(timezone.now().year)

    def test_favorites_page_marks_current_year(self, client, user, books):
        client.force_login(user)
        html = client.get(reverse('favorites_ranking')).content.decode()
        assert self._marked_year(html) == str(timezone.now().year)

    def test_no_year_in_dropdown_when_no_books(self, client, user):
        """Без книг в списке нет и строки с галочкой — перечислять нечего."""
        client.force_login(user)
        html = client.get(reverse('index')).content.decode()

        assert 'Выбрать год' not in html

    def test_favorites_is_separate_menu_item(self, client, user, books):
        """«Любимые» — отдельный пункт меню, а не строка внутри списка годов."""
        client.force_login(user)
        html = client.get(reverse('index')).content.decode()

        label = '\u0421\u0430\u043c\u0430\u044f \u043b\u044e\u0431\u0438\u043c\u0430\u044f \u043a\u043d\u0438\u0433\u0430'
        assert label in html
        # пункт стоит рядом с «Главная», а не внутри выпадающего списка книг
        nav = re.search(r'<nav class="hidden md:flex.*?</nav>', html, re.DOTALL).group(0)
        dropdown = re.search(r'<div x-show="open".*?overflow-hidden">.*?</div>', nav, re.DOTALL).group(0)
        assert label not in dropdown

    def test_mobile_menu_shows_favorite_item(self, client, user, books):
        client.force_login(user)
        html = client.get(reverse('index')).content.decode()

        burger = re.search(r'<div x-data="\{ open: false \}" class="md:hidden.*?</div>\s*</div>',
                           html, re.DOTALL)
        assert burger and '\u0421\u0430\u043c\u0430\u044f \u043b\u044e\u0431\u0438\u043c\u0430\u044f \u043a\u043d\u0438\u0433\u0430' in burger.group(0)


@pytest.mark.django_db
class TestBookListByYear:
    @pytest.fixture
    def user(self):
        return User.objects.create_user(email='years@miran.local', password='password')

    @pytest.fixture
    def books(self):
        return [
            Book.objects.create(year=2026, month=1, title='Атомарные привычки',
                                author='Клир', short_description='D'),
            Book.objects.create(year=2026, month=2, title='Дюна',
                                author='Герберт', short_description='D'),
            Book.objects.create(year=2027, month=1, title='Алхимик',
                                author='Коэльо', short_description='D'),
        ]

    def test_book_list_without_year_shows_all_years(self, client, user, books):
        client.force_login(user)
        response = client.get(reverse('book_list'))

        assert response.status_code == 200
        assert response.context['year'] is None
        titles = {b.title for b in response.context['books']}
        assert titles == {'Атомарные привычки', 'Дюна', 'Алхимик'}

    def test_book_list_filtered_by_year(self, client, user, books):
        client.force_login(user)
        response = client.get(reverse('book_list_year', args=[2027]))

        assert response.status_code == 200
        assert response.context['year'] == 2027
        assert [b.title for b in response.context['books']] == ['Алхимик']

    def test_book_list_2026_excludes_2027(self, client, user, books):
        client.force_login(user)
        html = client.get(reverse('book_list_year', args=[2026])).content.decode()

        assert 'Атомарные привычки' in html
        assert 'Дюна' in html
        assert 'Алхимик' not in html

    def test_year_with_no_books_shows_empty_state(self, client, user, books):
        client.force_login(user)
        response = client.get(reverse('book_list_year', args=[2030]))

        assert response.status_code == 200
        assert list(response.context['books']) == []
        assert 'Книг за 2030 год пока нет' in response.content.decode()

    def test_books_grouped_by_year_descending(self, client, user, books):
        client.force_login(user)
        response = client.get(reverse('book_list'))

        grouped = response.context['books_by_year']
        assert [year for year, _ in grouped] == [2027, 2026]
        assert len(grouped[1][1]) == 2  # 2026 -> две книги

    def test_header_dropdown_lists_available_years(self, client, user, books):
        client.force_login(user)
        html = client.get(reverse('book_list')).content.decode()

        assert reverse('book_list_year', args=[2026]) in html
        assert reverse('book_list_year', args=[2027]) in html

    def test_header_dropdown_available_on_every_page(self, client, user, books):
        """Годы нужны в шапке на всех страницах — отдаёт контекстный процессор."""
        client.force_login(user)
        for name in ('index', 'book_list'):
            response = client.get(reverse(name))
            assert list(response.context['available_years']) == [2027, 2026]

    def test_header_dropdown_hidden_when_no_books(self, client, user):
        client.force_login(user)
        response = client.get(reverse('book_list'))

        assert list(response.context['available_years']) == []
        assert 'Выбрать год' not in response.content.decode()

    def test_book_list_requires_login(self, client, books):
        response = client.get(reverse('book_list_year', args=[2026]))
        assert response.status_code == 302
        assert '/login/' in response.url

    def test_year_is_not_a_valid_path_segment(self, client, user, books):
        client.force_login(user)
        # нечисловой год не подходит под <int:year> -> 404
        assert client.get('/books/year/abc/').status_code == 404

    def test_book_detail_url_does_not_collide_with_year(self, client, user, books):
        """Раньше books/<int:year>/ перехватывал books/<int:pk>/.

        Страница книги и список за год — разные адреса, обе страницы открываются.
        """
        client.force_login(user)
        book = books[0]

        detail = client.get(reverse('book_detail', args=[book.pk]))
        assert detail.status_code == 200
        assert 'Атомарные привычки' in detail.content.decode()

        year_page = client.get(reverse('book_list_year', args=[2026]))
        assert year_page.status_code == 200
        assert 'Книги 2026 года' in year_page.content.decode()


@pytest.mark.django_db
class TestIndexFilteredByCurrentYear:
    @pytest.fixture
    def user(self):
        return User.objects.create_user(email='index@miran.local', password='password')

    @pytest.fixture
    def now_year(self):
        return timezone.now().year

    def test_index_uses_calendar_year(self, client, user, now_year):
        client.force_login(user)
        response = client.get(reverse('index'))
        assert response.context['year'] == now_year

    def test_top_books_exclude_other_years(self, client, user, now_year):
        old_book = Book.objects.create(year=now_year - 1, month=1, title='Старая книга',
                                       author='Автор', short_description='D')
        Vote.objects.create(book=old_book, user=user, rating=10)

        new_book = Book.objects.create(year=now_year, month=1, title='Текущая книга',
                                       author='Автор', short_description='D')
        Vote.objects.create(book=new_book, user=user, rating=5)

        client.force_login(user)
        response = client.get(reverse('index'))

        # в карточке текущего года только его книги
        current_card = response.context['rating_cards'][0]
        assert current_card['year'] == now_year
        assert [b.title for b in current_card['books']] == ['Текущая книга']

    def test_rating_cards_order_current_year_first(self, client, user, now_year):
        for offset in (2, 1):
            book = Book.objects.create(year=now_year - offset, month=1,
                                       title=f'Книга {now_year - offset}',
                                       author='Автор', short_description='D')
            Vote.objects.create(book=book, user=user, rating=7)
        book = Book.objects.create(year=now_year, month=1, title='Книга текущего года',
                                   author='Автор', short_description='D')
        Vote.objects.create(book=book, user=user, rating=7)

        client.force_login(user)
        response = client.get(reverse('index'))

        assert [card['year'] for card in response.context['rating_cards']] == [
            now_year, now_year - 1, now_year - 2,
        ]

    def test_one_rating_card_per_year_with_top_three(self, client, user, now_year):
        for i in range(5):
            book = Book.objects.create(year=now_year, month=i + 1, title=f'Книга {i}',
                                       author='Автор', short_description='D')
            Vote.objects.create(book=book, user=user, rating=i + 5)

        client.force_login(user)
        response = client.get(reverse('index'))

        cards = response.context['rating_cards']
        assert len(cards) == 1
        # топ-3 по убыванию рейтинга
        assert [b.title for b in cards[0]['books']] == ['Книга 4', 'Книга 3', 'Книга 2']

    def test_tied_ratings_sorted_alphabetically(self, client, user, now_year):
        """При равном рейтинге порядок задаётся алфавитом, а не планом БД."""
        # три голоса дают каждой книге одинаковое среднее 26/3 = 8.6667
        votes = {'first': 9, 'second': 8, 'third': 9}
        others = [
            User.objects.create_user(email=f'{name}@miran.local', password='password')
            for name in ('second', 'third')
        ]
        for title in ('Сто лет одиночества', 'Малый Принц', 'Смерть Ивана Ильича'):
            book = Book.objects.create(year=now_year, month=1, title=title,
                                       author='Автор', short_description='D')
            Vote.objects.create(book=book, user=user, rating=votes['first'])
            for user_obj, rating in zip(others, (votes['second'], votes['third'])):
                Vote.objects.create(book=book, user=user_obj, rating=rating)

        client.force_login(user)
        response = client.get(reverse('index'))

        titles = [b.title for b in response.context['rating_cards'][0]['books']]
        assert titles == ['Малый Принц', 'Смерть Ивана Ильича', 'Сто лет одиночества']

    def test_book_tied_with_third_place_is_not_dropped(self, client, user, now_year):
        """Книга с тем же баллом, что и третье место, не выпадает из карточки.

        Регрессия: при [:3] четвёртая равная книга молча исчезала,
        потому что её положение определял план СУБД.
        """
        others = [
            User.objects.create_user(email=f'{name}@miran.local', password='password')
            for name in ('second', 'third')
        ]
        # четыре книги с одинаковым средним, пятая — строго ниже
        for index, title in enumerate(['Январьская', 'Февральская', 'Мартовская', 'Апрельская']):
            book = Book.objects.create(year=now_year, month=index + 1, title=title,
                                       author='Автор', short_description='D')
            for user_obj, rating in zip([user] + others, (9, 8, 9)):
                Vote.objects.create(book=book, user=user_obj, rating=rating)
        worse = Book.objects.create(year=now_year, month=5, title='Худшая',
                                    author='Автор', short_description='D')
        Vote.objects.create(book=worse, user=user, rating=1)

        client.force_login(user)
        response = client.get(reverse('index'))

        books = response.context['rating_cards'][0]['books']
        assert len(books) == 4
        assert 'Худшая' not in [b.title for b in books]

    def test_cards_cut_at_three_when_no_ties(self, client, user, now_year):
        """Без ничьих карточка остаётся ровно на 3 книги."""
        for index in range(6):
            book = Book.objects.create(year=now_year, month=index + 1,
                                       title=f'Книга {index}', author='Автор',
                                       short_description='D')
            Vote.objects.create(book=book, user=user, rating=10 - index)

        client.force_login(user)
        response = client.get(reverse('index'))
        assert len(response.context['rating_cards'][0]['books']) == 3

    def test_rating_card_skips_year_without_ratings(self, client, user, now_year):
        Book.objects.create(year=now_year, month=1, title='Без оценок',
                            author='Автор', short_description='D')
        rated = Book.objects.create(year=now_year, month=2, title='С оценкой',
                                    author='Автор', short_description='D')
        Vote.objects.create(book=rated, user=user, rating=5)

        client.force_login(user)
        response = client.get(reverse('index'))

        assert [card['year'] for card in response.context['rating_cards']] == [now_year]

    def test_rating_rounded_to_one_decimal(self, client, user, now_year):
        """Средний балл округляется до 1 знака, как в Book.average_rating.

        Разделитель в русской локали — запятая (8,5); он одинаков на всех
        страницах, потому что Django локализует вывод float в шаблонах.
        """
        book = Book.objects.create(year=now_year, month=1, title='Книга',
                                   author='Автор', short_description='D')
        Vote.objects.create(book=book, user=user, rating=9)
        Vote.objects.create(book=book, user=User.objects.create_user(
            email='second@miran.local', password='password'), rating=8)

        client.force_login(user)
        html = client.get(reverse('index')).content.decode()

        scores = re.findall(r'⭐\s*([\d.,]+)', html)
        assert scores == ['8,5']
        # без округления в шаблон попало бы 8.5 со многими знаками
        assert book.average_rating == 8.5

    def test_meetings_card_rendered_before_rating_cards(self, client, user, now_year):
        book = Book.objects.create(year=now_year, month=1, title='Книга',
                                   author='Автор', short_description='D')
        Vote.objects.create(book=book, user=user, rating=5)

        client.force_login(user)
        html = client.get(reverse('index')).content.decode()

        assert 'Анонсы встреч' in html
        assert html.index('Анонсы встреч') < html.index('Рейтинг книг')

    def test_index_empty_when_no_books_this_year(self, client, user, now_year):
        old_book = Book.objects.create(year=now_year - 5, month=1, title='Древняя книга',
                                        author='Автор', short_description='D')
        Vote.objects.create(book=old_book, user=user, rating=9)

        client.force_login(user)
        response = client.get(reverse('index'))

        # карточка рейтинга прошлого года остаётся, счётчика книг на главной больше нет
        assert [card['year'] for card in response.context['rating_cards']] == [now_year - 5]

    def test_index_has_no_hardcoded_year(self, client, user, now_year):
        """Год в шаблоне главной должен приходить из {{ year }}, а не из литерала.

        Проверяем исходник шаблона, а не вывод: сейчас календарный год равен 2026,
        поэтому в отрендеренной странице «2026» закономерно присутствует.
        """
        from pathlib import Path

        from django.conf import settings

        template = Path(settings.BASE_DIR) / 'templates' / 'club' / 'index.html'
        source = template.read_text(encoding='utf-8')

        assert 'Читай {{ books_count }}' in source
        assert "url 'book_list_year' year" in source
        # литерал 2026 в разметке главной больше встречаться не должен
        assert '2026' not in source

        client.force_login(user)
        response = client.get(reverse('index'))
        count = response.context['books_count']
        html = response.content.decode()
        assert f'Читай {count} ' in html
        assert reverse('book_list_year', args=[now_year]) in html

    def test_index_cta_leads_to_current_year_list(self, client, user, now_year):
        Book.objects.create(year=now_year, month=1, title='Книга',
                            author='Автор', short_description='D')
        client.force_login(user)
        response = client.get(reverse('index'))

        url = reverse('book_list_year', args=[now_year])
        assert url in response.content.decode()

    def test_header_books_link_follows_year_on_index(self, client, user, now_year):
        client.force_login(user)
        html = client.get(reverse('index')).content.decode()
        assert reverse('book_list_year', args=[now_year]) in html


@pytest.mark.django_db
class TestBookFiles:
    @pytest.fixture(autouse=True)
    def _isolated_media_root(self, settings, tmp_path):
        """Файлы тестов не должны попадать в боевой media/."""
        settings.MEDIA_ROOT = tmp_path

    @pytest.fixture
    def user(self):
        return User.objects.create_user(email='files@miran.local', password='password')

    @pytest.fixture
    def book(self):
        return Book.objects.create(
            month=4, title='Книга с файлами', author='Автор', short_description='D'
        )

    def _attach(self, book, name, file_type):
        """Создаёт вложение вместе с реальным файлом во временном хранилище."""
        from django.core.files.base import ContentFile

        attachment = BookAttachment(book=book, file_type=file_type)
        attachment.file.save(name, ContentFile(b'test content'), save=True)
        return attachment

    def test_book_page_field_removed(self):
        """Поле «Страница книги / Ссылка» удалено из модели."""
        field_names = {f.name for f in Book._meta.get_fields()}
        assert 'book_page' not in field_names

    def test_attachment_types_are_browser_openable_only(self):
        """Только PDF/MP3/MP4 — браузер открывает их без помощи Office."""
        choices = dict(BookAttachment.AttachmentType.choices)
        assert set(choices) == {'pdf', 'mp3', 'mp4'}
        assert choices['mp3'] == 'MP3'
        assert choices['mp4'] == 'MP4'

    @pytest.mark.parametrize('file_type', ['pdf', 'mp3', 'mp4'])
    def test_each_type_supported(self, client, book, user, file_type):
        attachment = self._attach(book, f'file.{file_type}', file_type)
        client.force_login(user)

        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()
        assert attachment.file.url in html
        assert f'file.{file_type}' in html

    def test_filename_displayed_as_link(self, client, book, user):
        attachment = self._attach(book, 'duna.pdf', 'pdf')
        client.force_login(user)

        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()
        # имя файла — текст ссылки, ведёт на сам файл и открывается в браузере
        assert re.search(
            rf'<a href="{re.escape(attachment.file.url)}"[^>]*>.*?duna\.pdf',
            html,
            re.DOTALL,
        )
        assert 'target="_blank"' in html

    def test_custom_title_takes_precedence_over_filename(self, client, book, user):
        attachment = self._attach(book, 'audio.mp3', 'mp3')
        attachment.title = 'Аудиоверсия главы 1'
        attachment.save()

        client.force_login(user)
        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()

        # текст ссылки — заданное название; имя файла остаётся только в URL
        assert re.search(
            r'<a href="[^"]*audio\.mp3"[^>]*>.*?Аудиоверсия главы 1', html, re.DOTALL
        )

    def test_missing_file_shows_placeholder(self, client, book, user):
        """Нет файла — серая заглушка, а не битая ссылка."""
        BookAttachment.objects.create(book=book, file_type='pdf')
        client.force_login(user)

        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()
        assert 'Файл не прикреплён' in html
        assert 'target="_blank"' not in html.split('Файлы книги')[1]

    def test_file_deleted_from_disk_shows_placeholder(self, client, book, user):
        """Запись в БД есть, файла на диске нет — тоже заглушка."""
        attachment = self._attach(book, 'ghost.mp4', 'mp4')
        attachment.file.storage.delete(attachment.file.name)

        assert attachment.has_file is False
        client.force_login(user)
        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()
        assert 'Файл не прикреплён' in html
        assert 'ghost.mp4' in html  # имя файла остаётся видимым

    def test_book_without_files_shows_hint(self, client, book, user):
        client.force_login(user)
        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()
        assert 'Файлы пока не прикреплены.' in html

    def test_has_file_reflects_storage(self, book):
        assert self._attach(book, 'present.pdf', 'pdf').has_file is True
        assert BookAttachment(book=book, file_type='mp3').has_file is False

    def test_file_url_empty_when_no_file(self, book):
        assert BookAttachment(book=book, file_type='mp3').file_url == ''

    def test_display_name_falls_back_to_filename(self, book):
        attachment = self._attach(book, 'named.mp4', 'mp4')
        assert attachment.display_name == 'named.mp4'
        attachment.title = 'Видео'
        assert attachment.display_name == 'Видео'

    def test_old_materials_heading_removed(self, client, book, user):
        """Старый блок «Материалы для повторения» заменён на «Файлы книги»."""
        self._attach(book, 'x.pdf', 'pdf')
        client.force_login(user)
        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()
        assert 'Файлы книги' in html
        assert 'Материалы для повторения' not in html

    def test_admin_can_add_attachment_inline(self, client, book, user):
        """Админ добавляет файл прямо на странице книги в админке."""
        User.objects.create_superuser(email='adminfiles@miran.local', password='password')
        admin = User.objects.get(email='adminfiles@miran.local')
        client.force_login(admin)

        response = client.get(f'/admin/club/book/{book.pk}/change/')
        assert response.status_code == 200
        assert 'bookattachment' in response.content.decode()

    def test_admin_attachment_form_offers_all_types(self, client, book):
        User.objects.create_superuser(email='admintypes@miran.local', password='password')
        admin = User.objects.get(email='admintypes@miran.local')
        client.force_login(admin)

        html = client.get(f'/admin/club/book/{book.pk}/change/').content.decode()
        for label in ('PDF', 'MP3', 'MP4'):
            assert f'>{label}</option>' in html or f'value="{label.lower()}"' in html
        # PPT убран: браузер его не откроет
        assert '>PPT</option>' not in html

    def test_legacy_ppt_row_does_not_break_page(self, client, book, user):
        """Старая запись с типом 'ppt' не должна ломать рендер страницы.

        choices не проверяются на уровне .save(), поэтому в базе может
        остаться значение, которого больше нет в списке.
        """
        attachment = self._attach(book, 'slides.ppt', 'pdf')
        BookAttachment.objects.filter(pk=attachment.pk).update(file_type='ppt')

        client.force_login(user)
        response = client.get(reverse('book_detail', args=[book.pk]))

        assert response.status_code == 200
        assert 'slides.ppt' in response.content.decode()


@pytest.mark.django_db
class TestCoverCompression:
    @pytest.fixture(autouse=True)
    def _isolated_media_root(self, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path

    @pytest.fixture
    def user(self):
        return User.objects.create_user(email='cover@miran.local', password='password')

    def _make_image(self, width, height, image_format='JPEG', name='cover.jpg',
                    color=(200, 40, 90)):
        """Готовит «загруженный» файл нужного размера прямо в памяти."""
        image = Image.new('RGB', (width, height), color)
        buffer = BytesIO()
        image.save(buffer, format=image_format)
        buffer.seek(0)
        content_type = 'image/png' if image_format == 'PNG' else 'image/jpeg'
        return SimpleUploadedFile(name, buffer.read(), content_type=content_type)

    def test_cover_is_compressed_on_save(self):
        """Большая обложка ужимается при сохранении книги."""
        from club.images import MAX_BYTES
        from club.models import Book as BookModel

        book = BookModel.objects.create(
            month=1, title='Книга', author='Автор', short_description='D'
        )
        book.cover_image.save('cover.jpg', self._make_image(3000, 4000), save=True)
        book.refresh_from_db()

        assert book.cover_image.size <= MAX_BYTES
        assert max(Image.open(book.cover_image.path).size) <= 1200

    def test_cover_saved_as_jpeg(self):
        from club.models import Book as BookModel

        book = BookModel.objects.create(
            month=1, title='Книга', author='Автор', short_description='D'
        )
        book.cover_image.save('cover.png', self._make_image(2000, 2000, 'PNG'), save=True)
        book.refresh_from_db()

        with Image.open(book.cover_image.path) as image:
            assert image.format == 'JPEG'
            assert image.mode == 'RGB'

    def test_png_transparency_becomes_white_background(self):
        """Прозрачность PNG заливается белым, а не остаётся чёрным."""
        from club.models import Book as BookModel

        transparent = Image.new('RGBA', (1500, 1500), (0, 0, 0, 0))
        buffer = BytesIO()
        transparent.save(buffer, format='PNG')
        buffer.seek(0)

        book = BookModel.objects.create(
            month=1, title='Книга', author='Автор', short_description='D'
        )
        book.cover_image.save('alpha.png', buffer, save=True)
        book.refresh_from_db()

        with Image.open(book.cover_image.path) as image:
            assert image.mode == 'RGB'
            assert image.convert('RGB').getpixel((0, 0)) == (255, 255, 255)

    def test_cover_not_recompressed_on_subsequent_save(self):
        from club.models import Book as BookModel

        book = BookModel.objects.create(
            month=1, title='Книга', author='Автор', short_description='D'
        )
        book.cover_image.save('cover.jpg', self._make_image(2000, 2500), save=True)
        book.refresh_from_db()

        name, size = book.cover_image.name, book.cover_image.size
        book.title = 'Другое название'
        book.save()
        book.refresh_from_db()

        assert book.cover_image.name == name
        assert book.cover_image.size == size

    def test_old_cover_file_removed_after_compression(self):
        import os

        from django.conf import settings

        from club.models import Book as BookModel

        book = BookModel.objects.create(
            month=1, title='Книга', author='Автор', short_description='D'
        )
        book.cover_image.save('cover.jpg', self._make_image(3000, 3000), save=True)
        book.refresh_from_db()

        covers = os.listdir(os.path.join(str(settings.MEDIA_ROOT), 'books', 'covers'))
        assert len(covers) == 1, 'исходный файл должен быть удалён после сжатия'

    def test_unsupported_format_rejected(self):
        from django.core.exceptions import ValidationError

        from club.images import compress_image

        with pytest.raises(ValidationError):
            compress_image(self._make_image(200, 200, 'GIF'))

    def test_compressed_name_always_jpg(self):
        from club.images import compressed_name

        assert compressed_name('books/covers/my_cover.PNG') == 'my_cover.jpg'
        assert compressed_name('no_extension') == 'no_extension.jpg'

    def test_small_cover_is_left_alone(self):
        """Мелкая картинка не пережимается без нужды."""
        from club.images import needs_compression

        book = Book.objects.create(
            month=1, title='Книга', author='Автор', short_description='D'
        )
        book.cover_image.save('small.jpg', self._make_image(300, 400), save=True)
        book.refresh_from_db()

        assert needs_compression(book.cover_image) is False

    def test_admin_form_rejects_unsupported_cover_extension(self):
        """Админка принимает только jpg/jpeg/png."""
        from club.admin import BookAdminForm

        book = Book.objects.create(
            month=1, title='Книга', author='Автор', short_description='D'
        )
        gif = self._make_image(200, 200, 'GIF', name='cover.gif')

        form = BookAdminForm(
            data={'year': 2026, 'month': 1, 'title': 'Книга',
                  'author': 'Автор', 'short_description': 'D'},
            files={'cover_image': gif},
            instance=book,
        )
        assert not form.is_valid()
        assert 'cover_image' in form.errors

    def test_admin_form_accepts_allowed_cover_extensions(self):
        from club.admin import BookAdminForm

        for extension in ('jpg', 'jpeg', 'png'):
            book = Book.objects.create(
                month=1, title='Книга', author='Автор', short_description='D'
            )
            upload = self._make_image(400, 500, name=f'cover.{extension}')

            form = BookAdminForm(
                data={'year': 2026, 'month': 1, 'title': 'Книга',
                      'author': 'Автор', 'short_description': 'D'},
                files={'cover_image': upload},
                instance=book,
            )
            assert form.is_valid(), form.errors

    def test_cover_rendered_fully_not_cropped(self, client, user):
        """Обложка показывается целиком: object-contain, а не object-cover."""
        book = Book.objects.create(
            month=1, title='Книга с обложкой', author='Автор', short_description='D'
        )
        book.cover_image.save('cover.jpg', self._make_image(1600, 2600), save=True)
        book.refresh_from_db()

        client.force_login(user)
        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()

        img = re.search(r'<img[^>]*cover_image[^>]*>|<img[^>]*covers/[^>]*>', html).group(0)
        assert 'object-contain' in img
        assert 'object-cover' not in img


@pytest.mark.django_db
class TestAdminYearTabs:
    @pytest.fixture
    def admin_client(self, client):
        User.objects.create_superuser(email='admin-tabs@miran.local', password='password')
        client.force_login(User.objects.get(email='admin-tabs@miran.local'))
        return client

    @pytest.fixture
    def books(self):
        for year in (2026, 2025):
            for month in (1, 2):
                Book.objects.create(year=year, month=month,
                                    title=f'Книга {year}-{month}', author='Автор',
                                    short_description='D')

    @staticmethod
    def _parse(html):
        """Плашки и книги из changelist админки."""
        block = html[html.find('miran-year-tabs'):]
        block = block[:block.find('</div>', block.find('miran-year-tabs__caption'))]
        tabs = [
            (label.strip(), 'is-active' in cls)
            for cls, label in re.findall(
                r'class="miran-year-tab([^"]*)"[^>]*>([^<]+)</a>', block
            )
        ]
        table = html[html.find('id="result_list"'):]
        table = table[:table.find('</table>')]
        titles = re.findall(r'<td class="field-title">([^<]*)</td>', table)
        return tabs, titles

    def test_tabs_show_all_years_descending(self, admin_client, books):
        html = admin_client.get('/admin/club/book/').content.decode()
        tabs, _ = self._parse(html)

        assert [label for label, _ in tabs] == ['Все годы', '2026', '2025']

    def test_all_years_tab_active_by_default(self, admin_client, books):
        html = admin_client.get('/admin/club/book/').content.decode()
        tabs, titles = self._parse(html)

        active = [label for label, is_active in tabs if is_active]
        assert active == ['Все годы']
        assert len(titles) == 4

    def test_year_tab_filters_books(self, admin_client, books):
        html = admin_client.get('/admin/club/book/?year=2025').content.decode()
        tabs, titles = self._parse(html)

        assert [label for label, is_active in tabs if is_active] == ['2025']
        assert sorted(titles) == ['Книга 2025-1', 'Книга 2025-2']

    def test_selected_year_tab_is_marked_active(self, admin_client, books):
        response = admin_client.get('/admin/club/book/?year=2026')
        html = response.content.decode()
        assert 'aria-current="page"' in html

    def test_tab_links_point_to_admin_changelist(self, admin_client, books):
        html = admin_client.get('/admin/club/book/').content.decode()
        hrefs = re.findall(r'<a href="([^"]*)"[^>]*class="miran-year-tab', html)
        assert hrefs == [
            '/admin/club/book/',
            '/admin/club/book/?year=2026',
            '/admin/club/book/?year=2025',
        ]

    def test_tab_url_preserves_other_params(self, admin_client, books):
        """Выбор года не сбрасывает поиск и фильтр по месяцу."""
        html = admin_client.get('/admin/club/book/?month=2&year=2025').content.decode()
        href = re.search(r'href="([^"]*)"[^>]*class="miran-year-tab[^"]*"[^>]*>2026<', html).group(1)

        assert 'month=2' in href
        assert 'year=2026' in href

    def test_tab_url_drops_pagination(self, admin_client, books):
        html = admin_client.get('/admin/club/book/?p=2').content.decode()
        hrefs = re.findall(r'<a href="([^"]*)"[^>]*class="miran-year-tab', html)
        assert all('p=' not in href for href in hrefs)

    @pytest.mark.parametrize('query', ['?year=abc', '?year=', '?year=1999'])
    def test_invalid_year_redirects_to_clean_url(self, admin_client, books, query):
        """Мусорный год не должен приводить к странице «Ошибка настройки»."""
        response = admin_client.get('/admin/club/book/' + query)
        assert response.status_code == 302
        assert response['Location'] == '/admin/club/book/'

    def test_year_not_duplicated_in_sidebar_filters(self, admin_client, books):
        """Год убран из list_filter — в панели остался только месяц."""
        html = admin_client.get('/admin/club/book/').content.decode()
        panel = html[html.find('id="changelist-filter"'):]
        panel = panel[:panel.find('</search>')]

        assert 'Месяц' in panel
        assert 'Год' not in panel

    def test_month_filter_still_works_with_year_tab(self, admin_client, books):
        html = admin_client.get('/admin/club/book/?month=1&year=2025').content.decode()
        _, titles = self._parse(html)
        assert titles == ['Книга 2025-1']

    def test_tabs_placed_below_search_and_above_results(self, admin_client, books):
        """Плашки стоят под строкой поиска и выше списка книг."""
        html = admin_client.get('/admin/club/book/?year=2026').content.decode()

        search_start = html.find('<form id="changelist-search"')
        search_end = html.find('</form>', search_start)
        tabs_pos = html.find('miran-year-tabs')
        results_pos = html.find('id="result_list"')

        assert search_start != -1, 'форма поиска пропала'
        assert search_end != -1
        assert tabs_pos != -1, 'плашки не отрисовались'
        assert search_end < tabs_pos < results_pos

    def test_tabs_outside_search_form(self, admin_client, books):
        """Плашки не должны оказаться внутри формы поиска."""
        html = admin_client.get('/admin/club/book/').content.decode()
        form_start = html.find('<form id="changelist-search"')
        form_end = html.find('</form>', form_start)
        assert html.find('miran-year-tabs') > form_end

    def test_search_keeps_selected_year(self, admin_client, books):
        """Поиск внутри выбранного года не сбрасывает фильтр."""
        html = admin_client.get('/admin/club/book/?year=2025').content.decode()
        assert 'name="year" value="2025"' in html

    def test_tabs_not_inside_sidebar_filters(self, admin_client, books):
        """Плашки не попали в боковую панель фильтров."""
        html = admin_client.get('/admin/club/book/').content.decode()
        panel_start = html.find('id="changelist-filter"')
        panel_end = html.find('</search>', panel_start)
        assert not (panel_start < html.find('miran-year-tabs') < panel_end)

    def test_stylesheet_is_shipped(self, admin_client, books):
        from django.conf import settings

        html = admin_client.get('/admin/club/book/').content.decode()
        assert 'admin_year_tabs.css' in html
        assert (settings.BASE_DIR / 'static' / 'club' / 'admin_year_tabs.css').exists()

    def test_single_year_admin_still_shows_tabs(self, admin_client):
        """С одним годом в базе плашки всё равно строятся."""
        Book.objects.create(year=2030, month=1, title='Одна книга',
                            author='Автор', short_description='D')
        html = admin_client.get('/admin/club/book/').content.decode()
        tabs, titles = self._parse(html)

        assert [label for label, _ in tabs] == ['Все годы', '2030']
        assert titles == ['Одна книга']


@pytest.mark.django_db
class TestBookCardCover:
    @pytest.fixture(autouse=True)
    def _isolated_media_root(self, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path

    @pytest.fixture
    def user(self):
        return User.objects.create_user(email='cards@miran.local', password='password')

    @pytest.fixture
    def book(self):
        return Book.objects.create(
            year=2026, month=3, title='Книга с обложкой', author='Автор',
            short_description='D'
        )

    def _add_cover(self, book):
        from io import BytesIO

        from PIL import Image

        image = Image.new('RGB', (764, 1200), (20, 120, 40))
        buffer = BytesIO()
        image.save(buffer, format='JPEG')
        buffer.seek(0)
        book.cover_image.save('cover.jpg', buffer, save=True)
        book.refresh_from_db()
        return book

    def test_card_shows_cover_thumbnail(self, client, user, book):
        self._add_cover(book)
        client.force_login(user)

        html = client.get(reverse('book_list_year', args=[2026])).content.decode()
        img = re.search(r'<img[^>]*covers/[^>]*>', html).group(0)

        assert 'object-contain' in img, 'обложка должна показываться целиком'
        assert 'object-cover' not in img
        assert book.cover_image.url in img
        assert 'loading="lazy"' in img
        assert f'alt="{book.title}"' in img

    def test_cover_thumbnail_links_to_book_page(self, client, user, book):
        self._add_cover(book)
        client.force_login(user)

        html = client.get(reverse('book_list_year', args=[2026])).content.decode()
        href = re.search(
            r'<a href="([^"]+)"[^>]*class="block bg-gray-100', html
        ).group(1)
        assert href == reverse('book_detail', args=[book.pk])

    def test_month_strip_is_above_cover_and_title(self, client, user, book):
        """Порядок в карточке: месяц и балл → обложка → название."""
        self._add_cover(book)
        client.force_login(user)

        html = client.get(reverse('book_list_year', args=[2026])).content.decode()
        card = html[html.find('rounded-2xl shadow hover:shadow-lg'):]
        card = card[:card.find('</h3>')]

        month_pos = card.find('px-4 py-2')
        cover_pos = card.find('<img src="/media/books/covers/')
        title_pos = card.find('<h3')

        assert month_pos < cover_pos < title_pos

    def test_month_strip_keeps_user_rating(self, client, user, book):
        """Плашка месяца по-прежнему показывает оценку пользователя."""
        self._add_cover(book)
        Vote.objects.create(book=book, user=user, rating=8)
        client.force_login(user)

        html = client.get(reverse('book_list_year', args=[2026])).content.decode()
        # полоска месяца — единственный блок с такой комбинацией классов
        marker = 'bg-[#707372] text-white px-4 py-2'
        start = html.find(marker)
        assert start != -1, 'полоска месяца не найдена'
        month_strip = html[start:html.find('</div>', start)]

        assert 'Март' in month_strip
        assert 'Ваш балл: 8' in month_strip

    def test_book_without_cover_shows_placeholder(self, client, user, book):
        client.force_login(user)
        html = client.get(reverse('book_list_year', args=[2026])).content.decode()

        assert '📕 Март' in html
        assert 'bg-gray-100 border-b' in html

    def test_placeholder_shown_for_books_without_cover_only(self, client, user, book):
        with_cover = self._add_cover(book)
        without_cover = Book.objects.create(
            year=2026, month=4, title='Без обложки', author='Автор',
            short_description='D'
        )
        client.force_login(user)

        html = client.get(reverse('book_list_year', args=[2026])).content.decode()
        assert html.count('📕') == 1
        assert f'alt="{with_cover.title}"' in html
        assert f'alt="{without_cover.title}"' not in html

    def test_covers_shown_on_all_years_page(self, client, user, book):
        self._add_cover(book)
        Book.objects.create(year=2025, month=1, title='Прошлогодняя', author='А',
                            short_description='D')
        client.force_login(user)

        html = client.get(reverse('book_list')).content.decode()
        assert '<img src="/media/books/covers/' in html
        assert '📕' in html


@pytest.mark.django_db
class TestHeroBanner:
    @pytest.fixture
    def user(self):
        return User.objects.create_user(email='hero@miran.local', password='p')

    def test_banner_uses_picture_with_both_images(self, client, user):
        client.force_login(user)
        html = client.get(reverse('index')).content.decode()

        assert 'hero-desktop.jpg' in html
        assert 'hero-mobile.jpg' in html
        # мобильный вариант отдаётся через media-атрибут
        assert re.search(r'<source[^>]*hero-mobile\.jpg[^>]*>', html)
        assert '<picture>' in html

    def test_banner_image_is_decorative(self, client, user):
        """Баннер — украшение, поэтому alt пустой."""
        client.force_login(user)
        html = client.get(reverse('index')).content.decode()

        img = re.search(r'<img[^>]*hero-desktop\.jpg[^>]*>', html).group(0)
        assert 'alt=""' in img
        assert 'object-cover' in img

    def test_banner_keeps_dynamic_content(self, client, user):
        """Год и ссылка остаются в HTML — картинка их не заменяет."""
        Book.objects.create(year=timezone.now().year, month=1, title='Книга',
                            author='Автор', short_description='D')
        client.force_login(user)
        html = client.get(reverse('index')).content.decode()

        assert 'Смотреть книги' in html
        assert str(timezone.now().year) in html
        assert 'Добро пожаловать' in html
        # счётчик книг из баннера убран по требованию заказчика
        assert 'Книг в программе' not in html

    def test_banner_book_count_matches_current_year(self, client, user):
        """Число книг в тексте баннера берётся из БД, а не зашито в шаблон."""
        year = timezone.now().year
        for month in range(1, 5):
            Book.objects.create(year=year, month=month, title=f'Книга {month}',
                                author='Автор', short_description='D')
        Book.objects.create(year=year - 3, month=1, title='Прошлый год',
                            author='Автор', short_description='D')

        client.force_login(user)
        response = client.get(reverse('index'))

        assert response.context['books_count'] == 4
        assert 'Читай 4 книги' in response.content.decode()

    def test_banner_book_count_is_one_when_single_book(self, client, user):
        """Одна книга — «1 книга», а не «1 книг»."""
        Book.objects.create(year=timezone.now().year, month=1, title='Одна',
                            author='Автор', short_description='D')

        client.force_login(user)
        response = client.get(reverse('index'))
        assert 'Читай 1 книга' in response.content.decode()

    def test_banner_files_exist(self):
        from django.conf import settings

        base = settings.BASE_DIR / 'static' / 'images'
        assert (base / 'hero-desktop.jpg').exists()
        assert (base / 'hero-mobile.jpg').exists()

    def test_banner_image_sizes_match_measured_banner(self):
        """Размеры подобраны под реальные пропорции баннера в браузере.

        Десктоп 1240x272 (4.56:1) и мобильный 353x564 (0.63:1) — в 2x.
        """
        from django.conf import settings
        from PIL import Image

        base = settings.BASE_DIR / 'static' / 'images'
        with Image.open(base / 'hero-desktop.jpg') as desktop:
            assert desktop.size == (2480, 544)
        with Image.open(base / 'hero-mobile.jpg') as mobile:
            assert mobile.size == (800, 1250)


@pytest.mark.django_db
class TestFavoriteBook:
    """Сердечко «самая любимая книга»: одна на пользователя, переносится."""

    @pytest.fixture
    def user(self):
        return User.objects.create_user(email='fav@miran.local', password='p')

    @pytest.fixture
    def other_user(self):
        return User.objects.create_user(email='fav2@miran.local', password='p')

    @pytest.fixture
    def book(self):
        return Book.objects.create(year=2026, month=1, title='Книга',
                                    author='Автор', short_description='D')

    def test_heart_sets_favorite(self, client, user, book):
        client.force_login(user)
        response = client.post(reverse('toggle_favorite', args=[book.pk]))

        assert response.status_code == 302
        assert user.favorite.book_id == book.pk

    def test_second_book_moves_heart_from_first(self, client, user, book):
        """Главный сценарий: передумал — сердечко переехало, старое снято."""
        second = Book.objects.create(year=2026, month=2, title='Другая',
                                     author='Автор', short_description='D')
        client.force_login(user)
        client.post(reverse('toggle_favorite', args=[book.pk]))
        client.post(reverse('toggle_favorite', args=[second.pk]))

        assert user.favorite.book_id == second.pk
        # у книги должно быть ровно 0 сердечек, а не 1 у первой и 1 у второй
        assert book.favorited_by.count() == 0
        assert second.favorited_by.count() == 1
        assert Favorite.objects.filter(user=user).count() == 1

    def test_repeated_click_removes_heart(self, client, user, book):
        client.force_login(user)
        client.post(reverse('toggle_favorite', args=[book.pk]))
        client.post(reverse('toggle_favorite', args=[book.pk]))

        assert not Favorite.objects.filter(user=user).exists()
        assert book.favorited_by.count() == 0

    def test_user_cannot_have_two_favorites_in_db(self, user, book):
        """Ограничение «одна на пользователя» держит сама БД, а не код."""
        second = Book.objects.create(year=2026, month=3, title='Третья',
                                     author='Автор', short_description='D')
        Favorite.objects.create(user=user, book=book)

        with pytest.raises(IntegrityError):
            Favorite.objects.create(user=user, book=second)

    def test_others_hearts_counted_separately(self, client, user, other_user, book):
        """Сердечки разных участников не мешают друг другу."""
        client.force_login(user)
        client.post(reverse('toggle_favorite', args=[book.pk]))
        client.force_login(other_user)
        client.post(reverse('toggle_favorite', args=[book.pk]))

        assert book.favorited_by.count() == 2
        assert user.favorite.book_id == book.pk
        assert other_user.favorite.book_id == book.pk

    def test_toggle_requires_post(self, client, user, book):
        """Переход по ссылке не должен менять выбор: только POST."""
        client.force_login(user)
        response = client.get(reverse('toggle_favorite', args=[book.pk]))

        assert response.status_code == 405
        assert not Favorite.objects.filter(user=user).exists()

    def test_toggle_requires_login(self, client, book):
        response = client.post(reverse('toggle_favorite', args=[book.pk]))
        assert response.status_code == 302
        assert not Favorite.objects.exists()

    def test_toggle_unknown_book_404(self, client, user):
        client.force_login(user)
        assert client.post(reverse('toggle_favorite', args=[99999])).status_code == 404

    def test_redirects_back_to_page_it_came_from(self, client, user, book):
        """После нажатия на карточке списка возвращаем в список, а не на страницу книги."""
        client.force_login(user)
        response = client.post(
            reverse('toggle_favorite', args=[book.pk]),
            {'next': reverse('book_list')},
        )
        assert response.url == reverse('book_list')

    def test_redirect_ignores_foreign_next_url(self, client, user, book):
        """Чужой адрес в ?next= не должен превращаться в открытый редирект."""
        client.force_login(user)
        response = client.post(
            reverse('toggle_favorite', args=[book.pk]),
            {'next': 'https://evil.example/steal'},
        )
        assert 'evil.example' not in response.url
        assert response.url == reverse('book_detail', args=[book.pk])

    def test_heart_filled_on_own_book_page(self, client, user, book):
        client.force_login(user)
        client.post(reverse('toggle_favorite', args=[book.pk]))

        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()
        assert 'aria-pressed="true"' in html
        assert 'fill="currentColor"' in html

    def test_heart_outline_when_no_favorite(self, client, user, book):
        client.force_login(user)
        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()
        assert 'aria-pressed="false"' in html

    def test_heart_count_shown_on_book_page(self, client, user, other_user, book):
        client.force_login(user)
        client.post(reverse('toggle_favorite', args=[book.pk]))
        client.force_login(other_user)
        client.post(reverse('toggle_favorite', args=[book.pk]))

        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()
        assert '2 участника' in html

    def test_book_list_shows_own_heart_state(self, client, user, book):
        client.force_login(user)
        client.post(reverse('toggle_favorite', args=[book.pk]))

        html = client.get(reverse('book_list')).content.decode()
        assert 'aria-pressed="true"' in html

    def test_ranking_orders_by_hearts_then_title(self, client, user, book):
        """Равные сердечки не должны «прыгать»: вторичный ключ — алфавит."""
        alpha = Book.objects.create(year=2026, month=2, title='Альфа',
                                    author='Автор', short_description='D')
        beta = Book.objects.create(year=2026, month=3, title='Бета',
                                   author='Автор', short_description='D')
        def heart(book_pk):
            # отдельный email на каждого: пользователь с одним адресом
            # перестал бы быть отдельным участником с отдельным сердечком
            fan = User.objects.create_user(
                email=f'fan{len(Favorite.objects.all())}@miran.local', password='p'
            )
            client.force_login(fan)
            client.post(reverse('toggle_favorite', args=[book_pk]))

        for _ in range(3):
            heart(book.pk)
        for _ in range(2):
            heart(alpha.pk)
        heart(beta.pk)

        client.force_login(user)
        response = client.get(reverse('favorites_ranking'))

        titles = [b.title for b in response.context['books']]
        assert titles[0] == 'Книга'          # 3 сердечка
        assert titles[1:3] == ['Альфа', 'Бета']  # по 2, дальше по алфавиту
        assert response.context['books'][0].hearts == 3

    def test_ranking_lists_only_hearted_books(self, client, user):
        Book.objects.create(year=2026, month=1, title='Без сердечек',
                            author='Автор', short_description='D')
        client.force_login(user)
        response = client.get(reverse('favorites_ranking'))

        assert list(response.context['books']) == []

    def test_ranking_empty_page_has_prompt(self, client, user):
        client.force_login(user)
        html = client.get(reverse('favorites_ranking')).content.decode()

        assert 'Пока никто не отметил' in html
        assert 'список книг' in html

    def test_ranking_shows_who_marked_what(self, client, user, book):
        client.force_login(user)
        client.post(reverse('toggle_favorite', args=[book.pk]))

        html = client.get(reverse('favorites_ranking')).content.decode()
        assert 'Кто что отметил' in html
        assert 'fav@miran.local' in html

    def test_ranking_shows_my_choice(self, client, user, book):
        client.force_login(user)
        client.post(reverse('toggle_favorite', args=[book.pk]))

        html = client.get(reverse('favorites_ranking')).content.decode()
        assert 'Мой выбор' in html
        assert 'Сейчас ваша любимая книга' in html

    def test_ranking_prompts_when_no_choice(self, client, user):
        client.force_login(user)
        html = client.get(reverse('favorites_ranking')).content.decode()
        assert 'Вы ещё не выбрали любимую книгу' in html

    def test_ranking_requires_login(self, client):
        response = client.get(reverse('favorites_ranking'))
        assert response.status_code == 302

    def test_nav_links_to_ranking(self, client, user):
        client.force_login(user)
        html = client.get(reverse('index')).content.decode()
        assert reverse('favorites_ranking') in html

    def test_clearing_favorite_when_book_deleted(self, user, book):
        """Удаление книги не должно оставлять осиротевшее сердечко."""
        pk = book.pk
        book.delete()
        assert not Favorite.objects.filter(book_id=pk).exists()

    def test_clearing_favorite_when_user_deleted(self, user, book):
        Favorite.objects.create(user=user, book=book)
        user.delete()
        assert not Favorite.objects.exists()

    def test_str_shows_user_and_book(self, user, book):
        user.first_name, user.last_name = 'Иван', 'Петров'
        favorite = Favorite.objects.create(user=user, book=book)
        assert 'Петров Иван' in str(favorite)
        assert book.title in str(favorite)


@pytest.mark.django_db
class TestAuth:
    def test_registration_creates_user_and_logs_in(self, client):
        WhitelistEmail.objects.create(email='new@miran.local')
        response = client.post(
            reverse('register'),
            {'email': 'NEW@Miran.Local', 'password': 'strongpass123'},
        )
        assert response.status_code == 302
        assert response.url == reverse('index')
        # email сохраняется в нижнем регистре
        user = User.objects.get(email='new@miran.local')
        assert user.check_password('strongpass123')
        assert user.role == User.Role.PARTICIPANT

    def test_registration_rejected_when_not_in_whitelist(self, client):
        response = client.post(
            reverse('register'),
            {'email': 'stranger@miran.local', 'password': 'strongpass123'},
        )
        assert response.status_code == 200
        assert not User.objects.filter(email='stranger@miran.local').exists()
        assert 'белом списке' in response.content.decode()

    def test_registration_rejected_when_whitelist_entry_inactive(self, client):
        WhitelistEmail.objects.create(email='blocked@miran.local', is_active=False)
        response = client.post(
            reverse('register'),
            {'email': 'blocked@miran.local', 'password': 'strongpass123'},
        )
        assert response.status_code == 200
        assert not User.objects.exists()

    def test_registration_rejects_duplicate_email(self, client):
        WhitelistEmail.objects.create(email='dup@miran.local')
        User.objects.create_user(email='dup@miran.local', password='password')
        response = client.post(
            reverse('register'),
            {'email': 'dup@miran.local', 'password': 'strongpass123'},
        )
        assert response.status_code == 200
        assert User.objects.filter(email='dup@miran.local').count() == 1
        assert 'уже зарегистрирован' in response.content.decode()

    def test_login_by_email(self, client):
        WhitelistEmail.objects.create(email='login@miran.local')
        user = User.objects.create_user(email='login@miran.local', password='password123')
        response = client.post(
            reverse('login'),
            {'username': 'LOGIN@miran.local', 'password': 'password123'},
        )
        assert response.status_code == 302
        assert response.url == reverse('index')
        user.refresh_from_db()
        assert user.last_login is not None

    def test_login_rejected_when_not_in_whitelist(self, client):
        User.objects.create_user(email='stranger@miran.local', password='password123')
        response = client.post(
            reverse('login'),
            {'username': 'stranger@miran.local', 'password': 'password123'},
        )
        assert response.status_code == 200
        assert '_auth_user_id' not in client.session
        assert 'белом списке' in response.content.decode()

    def test_login_rejected_when_whitelist_removed_after_registration(self, client):
        WhitelistEmail.objects.create(email='removed@miran.local')
        User.objects.create_user(email='removed@miran.local', password='password123')
        WhitelistEmail.objects.filter(email='removed@miran.local').delete()
        response = client.post(
            reverse('login'),
            {'username': 'removed@miran.local', 'password': 'password123'},
        )
        assert response.status_code == 200
        assert '_auth_user_id' not in client.session

    def test_login_rejects_wrong_password(self, client):
        WhitelistEmail.objects.create(email='login@miran.local')
        User.objects.create_user(email='login@miran.local', password='password123')
        response = client.post(
            reverse('login'),
            {'username': 'login@miran.local', 'password': 'wrongpass'},
        )
        assert response.status_code == 200
        assert 'Неверный email или пароль' in response.content.decode()


@pytest.mark.django_db
class TestWhitelist:
    def test_email_normalized_to_lowercase_on_save(self):
        entry = WhitelistEmail.objects.create(email='  MiXeD@Miran.Local ')
        assert entry.email == 'mixed@miran.local'
        assert WhitelistEmail.objects.get(pk=entry.pk).email == 'mixed@miran.local'

    def test_email_normalized_to_lowercase_on_user_save(self):
        user = User.objects.create_user(email='  User@Miran.Local ', password='password')
        assert user.email == 'user@miran.local'
        user.email = '  Another@MIRAN.local '
        user.save()
        assert User.objects.get(pk=user.pk).email == 'another@miran.local'

    def test_is_allowed_ignores_case(self):
        WhitelistEmail.objects.create(email='allowed@miran.local')
        assert WhitelistEmail.is_allowed('ALLOWED@miran.local') is True
        assert WhitelistEmail.is_allowed('allowed@miran.local') is True

    def test_is_allowed_returns_false_for_inactive_and_empty(self):
        WhitelistEmail.objects.create(email='off@miran.local', is_active=False)
        assert WhitelistEmail.is_allowed('off@miran.local') is False
        assert WhitelistEmail.is_allowed('') is False
        assert WhitelistEmail.is_allowed(None) is False

    def test_is_allowed_returns_false_for_unknown(self):
        assert WhitelistEmail.is_allowed('unknown@miran.local') is False

    def test_normalize_email_helper(self):
        assert normalize_email('  TEST@Example.COM ') == 'test@example.com'
