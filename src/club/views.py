from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.db.models.functions import Lower
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import ReviewCommentForm, ReviewForm
from .models import Book, Favorite, Meeting, Review, Vote


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


def healthz_view(request):
    """Проверка живости для Docker HEALTHCHECK и балансировщика.

    Намеренно без логина и без похода в базу: проверка должна отвечать
    даже тогда, когда ещё не применены миграции или база занята записью.
    Иначе контейнер, который не может обслужить запрос, объявил бы себя
    больным и попал в рестарт-петлю.
    """
    return HttpResponse('ok')


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
        'books_count': Book.objects.filter(year=current_year).count(),
        'year': current_year,
        # Год для галочки в шапке: текущий, а если книг за него ещё нет —
        # ближайший, где они есть. Иначе в списке не отмечен был бы никто.
        'nav_year': current_year if current_year in years else (years[0] if years else current_year),
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

    # Любимая книга участника: id книги, если выбор сделан, иначе None
    my_favorite = getattr(request.user, 'favorite', None)
    my_favorite_id = my_favorite.book_id if my_favorite else None

    # Сколько участников отметило каждую книгу — одной выборкой по всем книгам
    hearts_by_book = dict(
        Favorite.objects.values_list('book_id').annotate(n=Count('user'))
    )
    # Флаг «сердечко стоит у меня» ставим на саму книгу: в шаблоне
    # {% if %} умеет сравнивать только с True/False, а не с book.pk.
    for book in books:
        book.hearts = hearts_by_book.get(book.pk, 0)
        book.is_favorite = book.pk == my_favorite_id

    context = {
        'books': books,
        'books_by_year': sorted(books_by_year.items(), reverse=True),
        'user_votes': user_votes,
        'year': year,
        # Флаг для шапки: открыт именно список всех годов, а не конкретный год
        'all_years': year is None,
        # При «всех годах» отмечать нечего — подсвечиваем самый свежий год
        'nav_year': year if year is not None else max(books_by_year, default=None),
        'my_favorite_id': my_favorite_id,
        'hearts_by_book': hearts_by_book,
    }
    return render(request, 'club/book_list.html', context)


@login_required
def book_detail_view(request, pk):
    book = get_object_or_404(Book, pk=pk)
    votes = book.votes.select_related('user').all()
    reviews = book.reviews.select_related('user').prefetch_related('comments__user').all()

    user_vote = book.votes.filter(user=request.user).first()

    # Число сердечек считаем в БД, а не через book.favorited_by.count()
    # на каждую книгу страницы: на главной это десятки лишних запросов.
    book.hearts = book.favorited_by.count()
    my_favorite = getattr(request.user, 'favorite', None)
    is_favorite = my_favorite is not None and my_favorite.book_id == book.pk

    if request.method == 'POST':
        # Handle voting
        if 'vote_rating' in request.POST:
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
        'form': form,
        'comment_forms': comment_forms,
        'is_favorite': is_favorite,
        'my_favorite': my_favorite,
    }
    return render(request, 'club/book_detail.html', context)


def _safe_next(request, book):
    """Куда вернуться после нажатия на сердечко.

    Адрес приходит из формы, то есть от пользователя, — пропускаем только
    относительные пути нашего же сайта, иначе это открытый редирект
    (префикс host/scheme Django сам отсекает).
    """
    target = request.POST.get('next') or ''
    if target and url_has_allowed_host_and_scheme(
        target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return target
    return reverse('book_detail', args=[book.pk])


@login_required
@require_POST
def toggle_favorite_view(request, pk):
    """Поставить или снять сердечко на обложке.

    Повторное нажатие на ту же книгу снимает выбор, нажатие на другую
    переносит его: у участника всегда остаётся ровно одна любимая книга.
    """
    book = get_object_or_404(Book, pk=pk)

    favorite = getattr(request.user, 'favorite', None)
    if favorite is not None and favorite.book_id == book.pk:
        favorite.delete()
    else:
        # update_or_create: при смене книги переносим ту же строку, а не
        # удаляем и вставляем заново — OneToOne всё равно не даст второй.
        Favorite.objects.update_or_create(
            user=request.user, defaults={'book': book}
        )

    return redirect(_safe_next(request, book))


@login_required
def favorites_ranking_view(request):
    """Рейтинг книг по сердечкам — сколько участников отметило каждую.

    Порядок: по числу сердечек, при равенстве по алфавиту, иначе равные
    книги «прыгали» бы между собой от запроса к запросу.
    """
    books = (
        Book.objects.annotate(hearts=Count('favorited_by'))
        .filter(hearts__gt=0)
        .order_by('-hearts', Lower('title'))
    )

    total_hearts = sum(book.hearts for book in books)
    favorites = (
        Favorite.objects.select_related('book', 'user')
        .order_by(Lower('user__last_name'), Lower('user__first_name'))
    )

    context = {
        'books': books,
        'total_hearts': total_hearts,
        'favorites_count': favorites.count(),
        'favorites': favorites,
        'my_favorite': getattr(request.user, 'favorite', None),
    }
    return render(request, 'club/favorites.html', context)


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
