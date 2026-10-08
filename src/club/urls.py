from django.urls import path

from . import views

urlpatterns = [
    path('', views.index_view, name='index'),
    path('books/', views.book_list_view, name='book_list'),
    # /books/year/2026/ — список книг за год. Отдельный префикс 'year' нужен,
    # потому что 'books/<int:pk>/' и 'books/<int:year>/' иначе совпали бы
    # и страница книги стала бы недостижимой.
    path('books/year/<int:year>/', views.book_list_view, name='book_list_year'),
    path('books/', views.book_list_view, name='books'),  # alias
    path('books/<int:pk>/', views.book_detail_view, name='book_detail'),
    path('reviews/<int:review_id>/edit/', views.edit_review_view, name='edit_review'),
    path(
        'reviews/<int:review_id>/comments/',
        views.add_review_comment_view,
        name='add_review_comment',
    ),
]
