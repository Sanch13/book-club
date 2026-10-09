import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env_bool(name, default=False):
    return os.environ.get(name, str(int(default))).strip().lower() in {'1', 'true', 'yes', 'on'}


def env_list(name, default=''):
    """Список из переменной окружения: 'a,b' -> ['a', 'b'].

    Пустая строка даёт пустой список, а не [''] — иначе Django
    счёл бы пустую строку допустимым хостом.
    """
    return [item.strip() for item in os.environ.get(name, default).split(',') if item.strip()]


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/

# Секрет обязателен: без него приложение не стартует. Раньше он был зашит
# в коде, и вместе с репозиторием уезжал на любой сервер, где его развернули.
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if env_bool('DJANGO_DEBUG', True):
        SECRET_KEY = 'django-insecure-dev-only-key-do-not-use-in-production'
    else:
        raise RuntimeError(
            'DJANGO_SECRET_KEY не задан. Сгенерируйте его: '
            'python -c "from django.core.management.utils import get_random_secret_key '
            'as g; print(g())"'
        )

# По умолчанию выключен: локально удобно включать через .env или DJANGO_DEBUG=1.
DEBUG = env_bool('DJANGO_DEBUG', False)

ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,[::1]')

# Локальные имена добавляем всегда: по ним ходит HEALTHCHECK контейнера
# (curl на 127.0.0.1:8000). Без этого проверка живости отвечала бы 400
# Bad Request и compose считал бы контейнер больным, перезапуская
# исправно работающее приложение.
ALLOWED_HOSTS = list(dict.fromkeys([*ALLOWED_HOSTS, 'localhost', '127.0.0.1', '[::1]']))


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'user',
    'club',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'club.context_processors.available_years',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        # Путь задаётся снаружи: в контейнере база лежит в отдельном томе
        # /app/data, а не рядом с кодом, который перезаписывается при деплое.
        'NAME': os.environ.get('DB_PATH') or BASE_DIR / 'db.sqlite3',
        'OPTIONS': {
            # WAL: читатели не блокируют писателя, а значит запросы
            # страниц не будут висеть во время загрузки файла в админке.
            'timeout': 20,
            'init_command': 'PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;',
        },
    }
}


# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = 'ru-ru'

TIME_ZONE = 'Europe/Moscow'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.1/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.environ.get('MEDIA_ROOT') or BASE_DIR / 'media'

# Загруженные файлы: клиент может прислать книгу на десятки мегабайт.
# Без этого лимита загрузка упала бы с 400/413 по памяти процесса.
MAX_UPLOAD_SIZE_MB = int(os.environ.get('MAX_UPLOAD_SIZE_MB', '200'))

# Прокси перед приложением (Nginx Proxy Manager) терминирует TLS,
# поэтому Django обязан доверять заголовку X-Forwarded-Proto — иначе
# request.is_secure() вернёт False, и secure-cookie не отправятся,
# а редиректы будут уходить на http:// вместо https://.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

# Браузер ходит по https (сертификат терминирует прокси), значит cookie
# можно и нужно помечать Secure — иначе они уедут открытым текстом.
SESSION_COOKIE_SECURE = env_bool('DJANGO_SECURE_COOKIES', not DEBUG)
CSRF_COOKIE_SECURE = env_bool('DJANGO_SECURE_COOKIES', not DEBUG)
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # не ломает JS-формы админки Django
SESSION_COOKIE_SAMESITE = 'Lax'

# CSRF проверяет Origin/Referer. Домен виден клиенту как https://book-club...,
# а Django получает запрос уже без схемы — без этого списка любой POST падал бы с 403.
CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_TRUSTED_ORIGINS')

# Метод, которым Django сам отвечает на HEAD/OPTIONS-проверки CSP,
# вызывается из middleware; оставляем стандартный.
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'

AUTH_USER_MODEL = 'user.User'
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'index'
LOGOUT_REDIRECT_URL = 'login'


# Email
# https://docs.djangoproject.com/en/6.1/topics/email/#topic-email-configuration

MAILERS = {
    'default': {
        'BACKEND': 'django.core.mail.backends.console.EmailBackend',
    },
}
