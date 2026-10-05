from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render

from .forms import LoginForm, RegistrationForm


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
