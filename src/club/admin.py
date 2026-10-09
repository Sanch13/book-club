from django import forms
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse

from .images import ALLOWED_EXTENSIONS
from .models import Book, BookAttachment, Favorite, Meeting, Review, ReviewComment, Vote


class BookAdminForm(forms.ModelForm):
    """Ограничивает формат обложки: принимаются только JPEG и PNG."""

    class Meta:
        model = Book
        fields = '__all__'

    def clean_cover_image(self):
        image = self.cleaned_data.get('cover_image')
        if not image:
            return image
        extension = image.name.rsplit('.', 1)[-1].lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise forms.ValidationError(
                'Обложка должна быть в формате JPEG или PNG (jpg, jpeg, png).'
            )
        return image


class BookAttachmentInline(admin.TabularInline):
    model = BookAttachment
    extra = 1
    fields = ('file_type', 'file', 'title')
    verbose_name = 'Файл книги'
    verbose_name_plural = 'Файлы книги'


class YearTabsFilterMixin:
    """Плашки выбора года над списком книг.

    Год убран из list_filter, чтобы не дублировать его и в плашках,
    и в боковой панели фильтров.
    """

    year_param = 'year'

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        selected = self.get_selected_year(request)
        if selected is not None:
            queryset = queryset.filter(year=selected)
        return queryset

    def get_selected_year(self, request):
        """Год из запроса, если он реально есть в базе. Мусор игнорируем."""
        raw = request.GET.get(self.year_param)
        if raw is None:
            return None
        try:
            year = int(raw)
        except (TypeError, ValueError):
            return None
        if year not in self.get_available_years():
            return None
        return year

    def get_available_years(self):
        return list(
            Book.objects.order_by('-year').values_list('year', flat=True).distinct()
        )

    def build_tabs(self, request):
        selected = self.get_selected_year(request)
        tabs = [
            {
                'year': None,
                'label': 'Все годы',
                'selected': selected is None,
                'url': self._tab_url(request, None),
            }
        ]
        for year in self.get_available_years():
            tabs.append({
                'year': year,
                'label': str(year),
                'selected': selected == year,
                'url': self._tab_url(request, year),
            })
        return tabs

    def _tab_url(self, request, year):
        query = request.GET.copy()
        query.pop(self.year_param, None)
        query.pop('p', None)  # при смене года страница пагинации сбрасывается
        if year is not None:
            query[self.year_param] = year
        path = reverse('admin:club_book_changelist')
        return f'{path}?{query.urlencode()}' if query else path


@admin.register(Book)
class BookAdmin(YearTabsFilterMixin, admin.ModelAdmin):
    form = BookAdminForm
    change_list_template = 'admin/book_changelist.html'
    list_display = ('month_name', 'title', 'author', 'year', 'average_rating', 'created_at')
    list_filter = ('month',)
    search_fields = ('title', 'author', 'short_description')
    inlines = [BookAttachmentInline]

    def changelist_view(self, request, extra_context=None):
        redirect_to = self._drop_bad_year(request)
        if redirect_to is not None:
            return HttpResponseRedirect(redirect_to)

        extra_context = {**(extra_context or {}), 'year_tabs': self.build_tabs(request)}
        return super().changelist_view(request, extra_context)

    def _drop_bad_year(self, request):
        """Убирает негодный ?year=, не давая админке показать «Ошибку настройки».

        Django считает неизвестный параметр фильтра некорректным и редиректит
        на ?e=1, а со второго запроса — отдаёт invalid_setup.html.
        """
        raw = request.GET.get(self.year_param)
        if raw is None or self.get_selected_year(request) is not None:
            return None
        query = request.GET.copy()
        query.pop(self.year_param, None)
        path = reverse('admin:club_book_changelist')
        return f'{path}?{query.urlencode()}' if query else path

    def month_name(self, obj):
        return obj.month_name
    month_name.short_description = 'Месяц'
    month_name.admin_order_field = 'month'

    class Media:
        css = {'all': ('club/admin_year_tabs.css',)}


@admin.register(BookAttachment)
class BookAttachmentAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'file_type', 'book', 'created_at')
    list_filter = ('file_type', 'book__year')
    search_fields = ('title', 'book__title')


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ('book', 'user', 'rating', 'updated_at')
    list_filter = ('book__year', 'rating')
    search_fields = ('user__email', 'book__title')


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    """Кто какую книгу считает самой любимой.

    Участника править нельзя: у него всегда ровно одна запись,
    и ручная правка book здесь — единственный способ её испортить.
    """

    list_display = ('user', 'book', 'created_at')
    list_filter = ('book__year',)
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'book__title')
    autocomplete_fields = ('book',)

    def has_add_permission(self, request):
        # Нового выбора делают сами участники с сайта
        return False


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('book', 'user', 'created_at', 'text_snippet')
    list_filter = ('book__year', 'created_at')
    search_fields = ('user__email', 'book__title', 'text')

    def text_snippet(self, obj):
        return obj.text[:50] + '...' if len(obj.text) > 50 else obj.text
    text_snippet.short_description = 'Текст отзыва'


@admin.register(ReviewComment)
class ReviewCommentAdmin(admin.ModelAdmin):
    list_display = ('review', 'user', 'text_snippet', 'created_at')
    list_filter = ('review__book__year', 'created_at')
    search_fields = ('user__email', 'text', 'review__text')

    def text_snippet(self, obj):
        return obj.text[:50] + '...' if len(obj.text) > 50 else obj.text
    text_snippet.short_description = 'Текст комментария'


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ('title', 'date_time', 'location')
    list_filter = ('date_time',)
    search_fields = ('title', 'location', 'description')
