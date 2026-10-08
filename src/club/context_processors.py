from .models import Book


def available_years(request):
    """Годы, за которые есть книги — для выпадающего списка в шапке.

    Шапка рендерится на каждой странице, поэтому годы проще отдать
    через контекстный процессор, чем прокидывать из каждого вьюха.
    """
    return {
        'available_years': list(
            Book.objects.order_by('-year').values_list('year', flat=True).distinct()
        )
    }