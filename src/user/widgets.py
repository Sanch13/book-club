from django import forms


class PasswordToggleInput(forms.PasswordInput):
    """Поле пароля с кнопкой-глазком для показа и скрытия значения.

    Виджет только подменяет шаблон рендера: разметка обёртки, иконки и
    переключение `type` живут в `user/widgets/password_toggle.html`.
    Без Alpine.js поле остаётся обычным полем пароля — глазок просто
    не нажимается, значение не показывается.
    """

    template_name = 'user/widgets/password_toggle.html'