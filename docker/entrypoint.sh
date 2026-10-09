#!/bin/sh
# Старт контейнера: подготовить базу и статику, затем передать управление gunicorn.
#
# exec обязателен: gunicorn должен стать PID 1 и получать SIGTERM от Docker,
# иначе остановка контейнера уходит в 10-секундный таймаут и SIGKILL —
# незавершённая запись в SQLite при этом теряется.

set -e

echo "==> Применяю миграции"
python manage.py migrate --noinput

echo "==> Собираю статику"
python manage.py collectstatic --noinput --clear

echo "==> Проверяю настройки"
python -c "from django.conf import settings; assert settings.SECRET_KEY; print('secret ok, hosts:', settings.ALLOWED_HOSTS)"

# Каталоги создаются в образе (Dockerfile) и переезжают в том вместе со
# своим владельцем, поэтому здесь ничего готовить не нужно: процесс и так
# работает от appuser, и chown от него невозможен.

echo "==> Запускаю gunicorn"
exec "$@"
