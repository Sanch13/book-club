from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm

from .models import User

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


class LoginForm(AuthenticationForm):
    username = forms.EmailField(
        label='Email',
        widget=forms.EmailInput(attrs=EMAIL_INPUT_ATTRS),
    )
    password = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs=PASSWORD_INPUT_ATTRS),
    )


class RegistrationForm(forms.Form):
    email = forms.EmailField(label='Email', widget=forms.EmailInput(attrs=EMAIL_INPUT_ATTRS))
    password = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs=NEW_PASSWORD_INPUT_ATTRS),
    )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        normalized = User._default_manager.normalize_email(email)
        if User.objects.filter(email__iexact=normalized).exists():
            raise forms.ValidationError('Пользователь с таким email уже зарегистрирован.')
        return normalized

    def clean_password(self):
        password = self.cleaned_data.get('password')
        password_validation.validate_password(password)
        return password

    def save(self):
        return User.objects.create_user(
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password'],
        )
