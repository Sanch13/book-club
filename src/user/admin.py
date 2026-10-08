from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin

from .models import User, WhitelistEmail, normalize_email


@admin.register(WhitelistEmail)
class WhitelistEmailAdmin(admin.ModelAdmin):
    list_display = ('email', 'is_active', 'comment', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('email', 'comment')
    ordering = ('email',)

    @admin.action(description='Активировать выбранные email')
    def activate_selected(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f'Активировано: {count}', messages.SUCCESS)

    @admin.action(description='Деактивировать выбранные email')
    def deactivate_selected(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f'Деактивировано: {count}', messages.WARNING)

    actions = [activate_selected, deactivate_selected]

    def save_model(self, request, obj, form, change):
        obj.email = normalize_email(obj.email)
        super().save_model(request, obj, form, change)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'role', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_active')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Персональные данные', {'fields': ('first_name', 'last_name')}),
        ('Права доступа', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Важные даты', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'role', 'password1', 'password2'),
        }),
    )
