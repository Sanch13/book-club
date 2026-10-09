from django.urls import path

from . import views

urlpatterns = [
    # Без логина: докер и прокси должны видеть живой контейнер до входа в сайт
    path('healthz/', views.healthz_view, name='healthz'),
    path('', views.index_view, name='index'),
    path('books/', views.book_list_view, name='book_list'),
    # /books/year/2026/ — список книг за год. Отдельный префикс 'year' нужен,
    # потому что 'books/<int:pk>/' и 'books/<int:year>/' иначе совпали бы
    # и страница книги стала бы недостижимой.
    path('books/year/<int:year>/', views.book_list_view, name='book_list_year'),
    path('books/', views.book_list_view, name='books'),  # alias
    path('books/<int:pk>/', views.book_detail_view, name='book_detail'),
    # Сердечко ставится только POST-ом: переход по ссылке не должен
    # менять выбор случайно (префетч в мобильных браузерах, копипаст ссылки).
    path(
        'books/<int:pk>/favorite/',
        views.toggle_favorite_view,
        name='toggle_favorite',
    ),
    path('favorites/', views.favorites_ranking_view, name='favorites_ranking'),
    path('reviews/<int:review_id>/edit/', views.edit_review_view, name='edit_review'),
    path(
        'reviews/<int:review_id>/comments/',
        views.add_review_comment_view,
        name='add_review_comment',
    ),
]
