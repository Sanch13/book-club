from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg
from django.db.models.functions import Lower
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ReviewCommentForm, ReviewForm
from .models import Book, Meeting, Review, Vote


def _top_with_ties(ranked, limit=3):
    """Первые `limit` книг плюс все, равные последней взятой по рейтингу.

    Без этого книга с тем же баллом, что и третье место, молча выпадала бы
    из карточки только из-за того, как СУБД вернула строки.

    Равенство сравнивается по точному среднему, а не по отображаемому:
    8.6667 и 8.7333 обе печатаются как «8,7», но ничьёй не являются.
    """
    top = list(ranked[:limit])
    if len(ranked) <= limit:
        return top

    cutoff = top[-1].rating_avg
    for book in ranked[limit:]:
        if book.rating_avg != cutoff:
            break
        top.append(book)
    return top


@login_required
def index_view(request):
    # Главная всегда показывает программу текущего календарного года
    current_year = timezone.now().year

    # Порядок карточек рейтинга: сначала текущий год, затем остальные по убыванию
    years = list(
        Book.objects.order_by('-year').values_list('year', flat=True).distinct()
    )
    ordered_years = ([current_year] if current_year in years else []) + [
        y for y in years if y != current_year
    ]

    # Одна выборка вместо запроса на каждую книгу: rating_avg считается в БД
    rated = Book.objects.annotate(rating_avg=Avg('votes__rating')).filter(
        year__in=ordered_years, rating_avg__isnull=False
    )
    # Вторичный ключ — алфавит, иначе порядок равных рейтингов задаёт план БД
    by_year = {}
    for book in rated.order_by('-rating_avg', Lower('title')):
        by_year.setdefault(book.year, []).append(book)

    rating_cards = []
    for card_year in ordered_years:
        ranked = by_year.get(card_year)
        if not ranked:
            continue
        top = _top_with_ties(ranked, limit=3)
        rating_cards.append({'year': card_year, 'books': top})

    meetings = Meeting.objects.filter(date_time__gte=timezone.now())[:3]

    context = {
        'meetings': meetings,
        'rating_cards': rating_cards,
        'total_books_count': Book.objects.filter(year=current_year).count(),
        'year': current_year,
    }
    return render(request, 'club/index.html', context)


@login_required
def book_list_view(request, year=None):
    """Список книг: за конкретный год (/books/year/2026/) или по всем годам (/books/)."""
    books = Book.objects.all().order_by('year', 'month')
    if year is not None:
        books = books.filter(year=year)

    # Группировка по годам нужна для вида «все годы»
    books_by_year = {}
    for book in books:
        books_by_year.setdefault(book.year, []).append(book)

    # Get user votes for current user
    user_votes = {v.book_id: v.rating for v in Vote.objects.filter(user=request.user)}

    context = {
        'books': books,
        'books_by_year': sorted(books_by_year.items(), reverse=True),
        'user_votes': user_votes,
        'year': year,
    }
    return render(request, 'club/book_list.html', context)


@login_required
def book_detail_view(request, pk):
    book = get_object_or_404(Book, pk=pk)
    votes = book.votes.select_related('user').all()
    reviews = book.reviews.select_related('user').prefetch_related('comments__user').all()
    
    # Check if voting deadline passed (end of 2026: 2026-12-31 23:59:59)
    voting_closed = timezone.now().year > 2026
    
    user_vote = book.votes.filter(user=request.user).first()

    if request.method == 'POST':
        # Handle voting
        if 'vote_rating' in request.POST:
            if voting_closed:
                return HttpResponseForbidden('Голосование завершено 31.12.2026.')
            try:
                rating = int(request.POST.get('vote_rating'))
                if 1 <= rating <= 10:
                    Vote.objects.update_or_create(
                        book=book,
                        user=request.user,
                        defaults={'rating': rating}
                    )
            except (ValueError, TypeError):
                pass
            return redirect('book_detail', pk=book.pk)

        # Handle review creation
        if 'review_text' in request.POST or 'text' in request.POST:
            form = ReviewForm(request.POST)
            if form.is_valid():
                review = form.save(commit=False)
                review.book = book
                review.user = request.user
                review.save()
                return redirect('book_detail', pk=book.pk)
    
    form = ReviewForm()
    # Форма комментария — своя для каждого отзыва на странице
    comment_forms = {review.pk: ReviewCommentForm() for review in reviews}

    context = {
        'book': book,
        'votes': votes,
        'reviews': reviews,
        'user_vote': user_vote,
        'voting_closed': voting_closed,
        'form': form,
        'comment_forms': comment_forms,
    }
    return render(request, 'club/book_detail.html', context)


@login_required
def add_review_comment_view(request, review_id):
    """Добавить комментарий к отзыву.

    Комментировать можно любой отзыв, включая свой собственный.
    Комментарии только создаются: правки и удаление не предусмотрены.
    """
    review = get_object_or_404(Review, pk=review_id)

    if request.method == 'POST':
        form = ReviewCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.review = review
            comment.user = request.user
            comment.save()
            return redirect('book_detail', pk=review.book.pk)
        # невалидная форма — показываем текст ошибки рядом с формой отзыва
        messages.error(request, 'Комментарий не может быть пустым.')
        return redirect('book_detail', pk=review.book.pk)

    return redirect('book_detail', pk=review.book.pk)


@login_required
def edit_review_view(request, review_id):
    review = get_object_or_404(Review, pk=review_id)
    if review.user != request.user:
        return HttpResponseForbidden('Вы можете редактировать только свои отзывы.')
    
    if request.method == 'POST':
        form = ReviewForm(request.POST, instance=review)
        if form.is_valid():
            form.save()
            return redirect('book_detail', pk=review.book.pk)
    else:
        form = ReviewForm(instance=review)
        
    context = {
        'form': form,
        'review': review,
        'book': review.book,
    }
    return render(request, 'club/edit_review.html', context)
