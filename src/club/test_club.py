import pytest
from django.urls import reverse
from club.models import Book, Review, User, Vote


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

        user1 = User.objects.create_user(login='user1', password='password')
        user2 = User.objects.create_user(login='user2', password='password')

        Vote.objects.create(book=book, user=user1, rating=8)
        Vote.objects.create(book=book, user=user2, rating=10)

        # Average of 8 and 10 is 9.0
        assert book.average_rating == 9.0

    def test_review_permissions(self, client):
        user1 = User.objects.create_user(login='author1', password='password')
        user2 = User.objects.create_user(login='author2', password='password')
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
        user = User.objects.create_user(login='voter1', password='password')
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
