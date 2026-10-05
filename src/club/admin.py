from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Book, BookAttachment, Meeting, Review, User, Vote


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('login', 'email', 'role', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_active')
    search_fields = ('login', 'email', 'first_name', 'last_name')
    ordering = ('login',)

    fieldsets = (
        (None, {'fields': ('login', 'password')}),
        ('Персональные данные', {'fields': ('first_name', 'last_name', 'email')}),
        ('Права доступа', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Важные даты', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('login', 'email', 'role', 'password1', 'password2'),
        }),
    )


class BookAttachmentInline(admin.TabularInline):
    model = BookAttachment
    extra = 1


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('month', 'title', 'author', 'year', 'average_rating', 'created_at')
    list_filter = ('year', 'month')
    search_fields = ('title', 'author', 'short_description')
    inlines = [BookAttachmentInline]


@admin.register(BookAttachment)
class BookAttachmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'book', 'file_type', 'created_at')
    list_filter = ('file_type', 'book__year')


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ('book', 'user', 'rating', 'updated_at')
    list_filter = ('book__year', 'rating')
    search_fields = ('user__login', 'book__title')


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('book', 'user', 'created_at', 'text_snippet')
    list_filter = ('book__year', 'created_at')
    search_fields = ('user__login', 'book__title', 'text')

    def text_snippet(self, obj):
        return obj.text[:50] + '...' if len(obj.text) > 50 else obj.text
    text_snippet.short_description = 'Текст отзыва'


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ('title', 'date_time', 'location')
    list_filter = ('date_time',)
    search_fields = ('title', 'location', 'description')
