from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render

from .forms import LoginForm, ProfileForm, ProfilePasswordForm, RegistrationForm


class CustomLoginView(LoginView):
    form_class = LoginForm
    template_name = 'user/login.html'
    redirect_authenticated_user = True


def register_view(request):
    if request.user.is_authenticated:
        return redirect('index')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            messages.success(request, 'Регистрация выполнена. Добро пожаловать в клуб!')
            return redirect('index')
    else:
        form = RegistrationForm()

    return render(request, 'user/register.html', {'form': form})


@login_required
def profile_view(request):
    """Личный кабинет: ФИО и смена пароля.

    Email не редактируется — он же логин, и по нему же проверяется белый список.
    """
    profile_form = ProfileForm(instance=request.user)
    password_form = ProfilePasswordForm(user=request.user)

    if request.method == 'POST':
        if 'save_profile' in request.POST:
            profile_form = ProfileForm(request.POST, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'Имя и фамилия сохранены.')
                return redirect('profile')
        elif 'change_password' in request.POST:
            password_form = ProfilePasswordForm(user=request.user, data=request.POST)
            if password_form.is_valid():
                password_form.save()
                # Иначе смена пароля разлогинила бы пользователя
                update_session_auth_hash(request, password_form.user)
                messages.success(request, 'Пароль изменён.')
                return redirect('profile')

    context = {'profile_form': profile_form, 'password_form': password_form}
    return render(request, 'user/profile.html', context)
