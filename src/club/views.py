from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ReviewForm
from .models import Book, Meeting, Review, Vote


@login_required
def index_view(request):
    # Overall book rankings by average rating
    books = Book.objects.all()
    # Filter books with ratings and sort by average rating descending
    ranked_books = sorted(
        [b for b in books if b.average_rating is not None],
        key=lambda x: x.average_rating,
        reverse=True
    )
    unrated_books = [b for b in books if b.average_rating is None]
    
    top_books = ranked_books[:3]
    meetings = Meeting.objects.filter(date_time__gte=timezone.now())[:3]

    context = {
        'top_books': top_books,
        'meetings': meetings,
        'total_books_count': books.count(),
    }
    return render(request, 'club/index.html', context)


@login_required
def book_list_view(request):
    books = Book.objects.all().order_by('month')
    # Get user votes for current user
    user_votes = {v.book_id: v.rating for v in Vote.objects.filter(user=request.user)}
    
    context = {
        'books': books,
        'user_votes': user_votes,
    }
    return render(request, 'club/book_list.html', context)


@login_required
def book_detail_view(request, pk):
    book = get_object_or_404(Book, pk=pk)
    votes = book.votes.select_related('user').all()
    reviews = book.reviews.select_related('user').all()
    
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
    
    context = {
        'book': book,
        'votes': votes,
        'reviews': reviews,
        'user_vote': user_vote,
        'voting_closed': voting_closed,
        'form': form,
    }
    return render(request, 'club/book_detail.html', context)


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
