from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

from .models import User, WhitelistEmail, normalize_email

EMAIL_INPUT_ATTRS = {
    'class': 'w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-[#A2D813]',
    'placeholder': 'you@example.com',
    'autocomplete': 'email',
}
PASSWORD_INPUT_ATTRS = {
    'class': 'w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-[#A2D813]',
    'autocomplete': 'current-password',
}
NEW_PASSWORD_INPUT_ATTRS = {
    'class': 'w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-[#A2D813]',
    'placeholder': 'Минимум 8 символов',
    'autocomplete': 'new-password',
}
TEXT_INPUT_ATTRS = {
    'class': 'w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-[#A2D813]',
}


NOT_IN_WHITELIST_ERROR = 'Этот email отсутствует в белом списке. Обратитесь к администратору.'


class LoginForm(AuthenticationForm):
    username = forms.EmailField(
        label='Email',
        widget=forms.EmailInput(attrs=EMAIL_INPUT_ATTRS),
    )
    password = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs=PASSWORD_INPUT_ATTRS),
    )

    def clean_username(self):
        email = normalize_email(self.cleaned_data.get('username'))
        if not WhitelistEmail.is_allowed(email):
            raise forms.ValidationError(NOT_IN_WHITELIST_ERROR)
        return email


class RegistrationForm(forms.Form):
    email = forms.EmailField(label='Email', widget=forms.EmailInput(attrs=EMAIL_INPUT_ATTRS))
    password = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs=NEW_PASSWORD_INPUT_ATTRS),
    )

    def clean_email(self):
        email = normalize_email(self.cleaned_data.get('email'))
        if not WhitelistEmail.is_allowed(email):
            raise forms.ValidationError(NOT_IN_WHITELIST_ERROR)
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Пользователь с таким email уже зарегистрирован.')
        return email

    def clean_password(self):
        password = self.cleaned_data.get('password')
        password_validation.validate_password(password)
        return password

    def save(self):
        return User.objects.create_user(
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password'],
        )


class ProfileForm(forms.ModelForm):
    """Личный кабинет: пользователь меняет только своё имя и фамилию."""

    # Поля объявлены явно, а не через Meta.widgets — как в LoginForm выше,
    # так в файле не появляется лишних RUF012
    first_name = forms.CharField(
        label='Имя',
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs=TEXT_INPUT_ATTRS | {
            'placeholder': 'Михаил',
            'autocomplete': 'given-name',
        }),
    )
    last_name = forms.CharField(
        label='Фамилия',
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs=TEXT_INPUT_ATTRS | {
            'placeholder': 'Булгаков',
            'autocomplete': 'family-name',
        }),
    )

    class Meta:
        model = User
        fields = ('first_name', 'last_name')

    def clean(self):
        """Пустая пара «имя + фамилия» равносильна отсутствию имени."""
        cleaned = super().clean()
        if not cleaned.get('first_name') and not cleaned.get('last_name'):
            self.add_error('first_name', 'Заполните оба поля или оставьте пустыми.')
        return cleaned


class ProfilePasswordForm(PasswordChangeForm):
    """Смена пароля с проверкой текущего."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_order = ('old_password', 'new_password1', 'new_password2')
        self.order_fields(field_order)
        attrs = PASSWORD_INPUT_ATTRS | {'autocomplete': 'current-password'}
        self.fields['old_password'].widget = forms.PasswordInput(attrs=attrs)
        self.fields['new_password1'].widget = forms.PasswordInput(
            attrs=NEW_PASSWORD_INPUT_ATTRS
        )
        self.fields['new_password2'].widget = forms.PasswordInput(
            attrs=NEW_PASSWORD_INPUT_ATTRS | {'placeholder': 'Повторите пароль'}
        )
        for name, label in (
            ('old_password', 'Текущий пароль'),
            ('new_password1', 'Новый пароль'),
            ('new_password2', 'Новый пароль ещё раз'),
        ):
            self.fields[name].label = label
