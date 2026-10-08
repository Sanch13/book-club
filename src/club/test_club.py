import pytest
from django.urls import reverse

from club.models import Book, Review, Vote
from user.models import User, WhitelistEmail, normalize_email


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
