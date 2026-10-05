from django.urls import path

from . import views

urlpatterns = [
    path('', views.index_view, name='index'),
    path('books/', views.book_list_view, name='book_list'),
    path('books/', views.book_list_view, name='books'),  # alias
    path('books/<int:pk>/', views.book_detail_view, name='book_detail'),
    path('reviews/<int:review_id>/edit/', views.edit_review_view, name='edit_review'),
]
