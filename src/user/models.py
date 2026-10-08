from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


def normalize_email(email):
    """Приводит email к нижнему регистру для надёжного сравнения и поиска."""
    return BaseUserManager.normalize_email(email or '').strip().lower()


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email must be set')
        email = normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Админ'
        PARTICIPANT = 'participant', 'Участник'

    username = None
    email = models.EmailField('Email', max_length=254, unique=True)
    role = models.CharField(
        'Роль',
        max_length=20,
        choices=Role.choices,
        default=Role.PARTICIPANT,
    )

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email

    @property
    def display_name(self):
        """Как показывать пользователя: «Фамилия Имя» или email.

        Имя показывается только если заполнены оба поля — иначе в списках
        отзывов вместо почты появлялись бы служебные значения вроде
        «Участник Клуба».
        """
        if self.first_name and self.last_name:
            return f'{self.last_name} {self.first_name}'
        return self.email

    def save(self, *args, **kwargs):
        self.email = normalize_email(self.email)
        super().save(*args, **kwargs)

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN


class WhitelistEmail(models.Model):
    """Белый список email: только эти адреса могут регистрироваться и входить."""

    email = models.EmailField('Email', max_length=254, unique=True)
    comment = models.CharField('Комментарий', max_length=255, blank=True)
    is_active = models.BooleanField('Активен', default=True)
    created_at = models.DateTimeField('Добавлен', auto_now_add=True)

    class Meta:
        ordering = ['email']
        verbose_name = 'Email в белом списке'
        verbose_name_plural = 'Белый список email'

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        self.email = normalize_email(self.email)
        super().save(*args, **kwargs)

    @classmethod
    def is_allowed(cls, email):
        """Проверяет, что email есть в белом списке (с учётом нижнего регистра)."""
        normalized = normalize_email(email)
        if not normalized:
            return False
        return cls.objects.filter(email=normalized, is_active=True).exists()
