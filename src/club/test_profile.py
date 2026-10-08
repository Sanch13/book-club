"""Тесты личного кабинета и отображения имени пользователя."""

import pytest
from django.urls import reverse

from club.models import Book, Review, ReviewComment, Vote
from user.models import User, WhitelistEmail


@pytest.mark.django_db
class TestDisplayName:
    def test_uses_surname_and_name(self):
        user = User.objects.create_user(
            email='a@miran.local', password='p',
            first_name='Михаил', last_name='Булгаков',
        )
        assert user.display_name == 'Булгаков Михаил'

    def test_falls_back_to_email_without_last_name(self):
        user = User.objects.create_user(
            email='b@miran.local', password='p', first_name='Михаил'
        )
        assert user.display_name == 'b@miran.local'

    def test_falls_back_to_email_without_first_name(self):
        user = User.objects.create_user(
            email='c@miran.local', password='p', last_name='Булгаков'
        )
        assert user.display_name == 'c@miran.local'

    def test_email_when_both_empty(self):
        user = User.objects.create_user(email='d@miran.local', password='p')
        assert user.display_name == 'd@miran.local'

    def test_whitelist_is_not_a_user(self):
        """У WhitelistEmail нет display_name — это разные сущности."""
        from user.models import WhitelistEmail

        entry = WhitelistEmail.objects.create(email='e@miran.local')
        assert not hasattr(entry, 'display_name')


@pytest.mark.django_db
class TestProfilePage:
    @pytest.fixture
    def user(self):
        return User.objects.create_user(
            email='profile@miran.local', password='password', first_name='Михаил'
        )

    def test_requires_login(self, client):
        response = client.get(reverse('profile'))
        assert response.status_code == 302
        assert '/login/' in response.url

    def test_opens_for_logged_in(self, client, user):
        client.force_login(user)
        response = client.get(reverse('profile'))

        assert response.status_code == 200
        html = response.content.decode()
        assert 'Личный кабинет' in html
        assert 'Имя' in html and 'Фамилия' in html

    def test_email_is_shown_but_not_editable(self, client, user):
        """Email — это логин, менять его нельзя и не нужно предлагать."""
        client.force_login(user)
        html = client.get(reverse('profile')).content.decode()

        assert user.email in html
        assert 'name="email"' not in html

    def test_saves_first_and_last_name(self, client, user):
        client.force_login(user)
        response = client.post(reverse('profile'), {
            'save_profile': '1',
            'first_name': 'Михаил',
            'last_name': 'Булгаков',
        })

        assert response.status_code == 302
        user.refresh_from_db()
        assert (user.first_name, user.last_name) == ('Михаил', 'Булгаков')
        assert user.display_name == 'Булгаков Михаил'

    def test_email_cannot_be_changed(self, client, user):
        client.force_login(user)
        client.post(reverse('profile'), {
            'save_profile': '1',
            'first_name': 'Михаил',
            'last_name': 'Булгаков',
            'email': 'hacker@miran.local',
        })

        user.refresh_from_db()
        assert user.email == 'profile@miran.local'

    def test_keeps_input_when_form_invalid(self, client, user):
        """При ошибке введённое не теряется."""
        client.force_login(user)
        response = client.post(reverse('profile'), {
            'save_profile': '1', 'first_name': 'Только имя', 'last_name': '',
        }, follow=True)

        assert 'value="Только имя"' in response.content.decode()

    def test_shows_how_user_is_seen(self, client, user):
        client.force_login(user)

        without_name = client.get(reverse('profile')).content.decode()
        assert user.email in without_name

        user.last_name = 'Булгаков'
        user.save()
        with_name = client.get(reverse('profile')).content.decode()
        assert 'Булгаков Михаил' in with_name

    def test_header_email_links_to_profile(self, client, user):
        client.force_login(user)
        html = client.get(reverse('index')).content.decode()
        assert f'href="{reverse("profile")}"' in html


@pytest.mark.django_db
class TestPasswordChange:
    @pytest.fixture
    def user(self):
        # без записи в белом списке вход не пройдёт: LoginForm его проверяет
        WhitelistEmail.objects.create(email='pwd@miran.local')
        return User.objects.create_user(email='pwd@miran.local', password='password')

    NEW = {
        'change_password': '1',
        'old_password': 'password',
        'new_password1': 'newpassword2026',
        'new_password2': 'newpassword2026',
    }

    def test_password_can_be_changed(self, client, user):
        client.force_login(user)
        response = client.post(reverse('profile'), self.NEW)

        assert response.status_code == 302
        user.refresh_from_db()
        assert user.check_password('newpassword2026')

    def test_stays_logged_in_after_change(self, client, user):
        """Без update_session_auth_hash Django разлогинил бы пользователя."""
        client.force_login(user)
        client.post(reverse('profile'), self.NEW)

        response = client.get(reverse('index'))
        assert response.status_code == 200
        assert reverse('logout') in response.content.decode()

    def test_new_password_works_for_next_login(self, client, user):
        client.force_login(user)
        client.post(reverse('profile'), self.NEW)

        client.logout()
        response = client.post(reverse('login'), {
            'username': 'pwd@miran.local', 'password': 'newpassword2026',
        })
        assert response.status_code == 302

    def test_old_password_stops_working(self, client, user):
        client.force_login(user)
        client.post(reverse('profile'), self.NEW)

        client.logout()
        response = client.post(reverse('login'), {
            'username': 'pwd@miran.local', 'password': 'password',
        })
        assert response.status_code == 200

    def test_wrong_current_password_rejected(self, client, user):
        client.force_login(user)
        response = client.post(reverse('profile'), self.NEW | {'old_password': 'нет'})

        assert response.status_code == 200
        user.refresh_from_db()
        assert user.check_password('password')

    def test_mismatched_confirmation_rejected(self, client, user):
        client.force_login(user)
        client.post(reverse('profile'), self.NEW | {'new_password2': 'другой2026'})

        user.refresh_from_db()
        assert user.check_password('password')


@pytest.mark.django_db
class TestNameInReviewsAndComments:
    @pytest.fixture
    def user(self):
        return User.objects.create_user(
            email='writer@miran.local', password='password', first_name='Михаил'
        )

    @pytest.fixture
    def book(self):
        return Book.objects.create(
            month=1, title='Книга', author='Автор', short_description='D'
        )

    def test_review_shows_name(self, client, user, book):
        user.last_name = 'Булгаков'
        user.save()
        Review.objects.create(book=book, user=user, text='Отзыв')

        client.force_login(user)
        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()
        reviews_block = html[html.find('Отзывы участников'):]
        assert 'Булгаков Михаил' in reviews_block
        # email автора отзыва заменён именем (в шапке сайта email остаётся)
        assert '👤 writer@miran.local' not in reviews_block

    def test_review_shows_email_when_name_incomplete(self, client, user, book):
        """Заполнено только имя — показываем email, а не «Михаил»."""
        Review.objects.create(book=book, user=user, text='Отзыв')

        client.force_login(user)
        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()
        assert 'writer@miran.local' in html

    def test_comment_shows_name(self, client, user, book):
        user.last_name = 'Булгаков'
        user.save()
        review = Review.objects.create(book=book, user=user, text='Отзыв')
        ReviewComment.objects.create(review=review, user=user, text='Комментарий')

        client.force_login(user)
        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()
        assert 'Булгаков Михаил' in html

    def test_votes_list_shows_name(self, client, user, book):
        """Список голосовавших подписан так же, как отзывы и комментарии."""
        user.last_name = 'Булгаков'
        user.save()
        Vote.objects.create(book=book, user=user, rating=8)

        client.force_login(user)
        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()
        votes_block = html[html.find('Кто как проголосовал'):]
        votes_block = votes_block[:votes_block.find('Отзывы участников')]

        assert 'Булгаков Михаил' in votes_block
        assert 'writer@miran.local' not in votes_block

    def test_votes_list_falls_back_to_email(self, client, user, book):
        """ФИО не заполнено — в списке голосов остаётся email."""
        Vote.objects.create(book=book, user=user, rating=8)

        client.force_login(user)
        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()
        votes_block = html[html.find('Кто как проголосовал'):]
        votes_block = votes_block[:votes_block.find('Отзывы участников')]

        assert 'writer@miran.local' in votes_block

    def test_other_participants_names_visible_to_each_other(self, client, book):
        """Имя одного участника видно другим."""
        author = User.objects.create_user(
            email='author2@miran.local', password='p',
            first_name='Анна', last_name='Ахматова',
        )
        reviewer = User.objects.create_user(email='rev@miran.local', password='p')
        review = Review.objects.create(book=book, user=author, text='Стихи')
        ReviewComment.objects.create(review=review, user=reviewer, text='Согласен')

        client.force_login(reviewer)
        html = client.get(reverse('book_detail', args=[book.pk])).content.decode()
        assert 'Ахматова Анна' in html