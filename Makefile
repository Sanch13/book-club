# makefile
DC = docker compose
D = docker
EXEC = docker exec -it
LOGS = docker logs
DC_FILE = docker-compose.yml
APP_CONTAINER = web
SERVICE_APP_NAME = web
SERVICE_NGINX_NAME = nginx

# Тег образа берём из .env — это единственный источник. Раньше он был
# ещё и в этой строке, и тогда можно было собрать одно, а задеплоить
# другое: compose читал .env, а сборка и push — Makefile. Переопределяется
# через переменную окружения, если понадобится.
IMAGE ?= $(shell sed -n 's/^IMAGE=//p' .env | tr -d '"' | head -1)

# Хост для проверок (make verify). Берётся из .env — там же, где его видит
# Django в ALLOWED_HOSTS, иначе проверка получит 400 и запутает.
DEPLOY_HOST ?= $(shell sed -n 's/^DJANGO_ALLOWED_HOSTS=//p' .env | tr -d '"' | head -1 | cut -d, -f1)

.PHONY: test
test:
	@uv run pytest -q

.PHONY: app
app:
	@$(MAKE) app-sync
	@${DC} -f ${DC_FILE} up --build -d

# ВНИМАНИЕ: `docker compose down -v` удаляет тома, а вместе с ними базу
# данных (db_data) и все медиафайлы (media_data) — молча и безвозвратно.
# Для штатной остановки используйте эту цель: `-v` здесь намеренно нет.
.PHONY: app-down
app-down:
	@${DC} -f ${DC_FILE} down

.PHONY: app-sync
app-sync:
	@uv sync

.PHONY: app-build
app-build:
	@${D} build -t ${IMAGE} .

.PHONY: app-push
app-push:
	@${D} push ${IMAGE}

.PHONY: app-test-rebuild-push
app-test-rebuild-push:
	@$(MAKE) test
	@$(MAKE) check-migrations
	@$(MAKE) app-del
	@$(MAKE) app-build
	@$(MAKE) app-push

.PHONY: app-del
app-del:
	@if ${D} image inspect ${IMAGE} >/dev/null 2>&1; then \
		${D} rmi ${IMAGE}; \
	fi

# Чистит только очевидный мусор. `-a`/`--all` не используется намеренно:
# он сносил бы предыдущий образ, который нужен для отката (см. target rollback).
# Тома не трогаем: в них база, медиа и собранная статика.
.PHONY: prune-safe
prune-safe:
	@${D} container prune -f
	@${D} builder prune -f --filter "until=168h"
	@${D} image prune -f --filter "until=168h"
	@echo "Тома (db_data, media_data, static_data) не тронуты."

# Миграции создаются и применяются ТОЛЬКО локально. В контейнере делать
# это нельзя: src/ там часть образа, а не том, поэтому созданный файл
# миграции исчез бы при следующем пересоздании контейнера.
# На сервере миграции применяет entrypoint при старте (docker/entrypoint.sh),
# до gunicorn — отдельного шага деплоя не требуется.
.PHONY: makemigrations
makemigrations:
	@.venv/bin/python manage.py makemigrations

.PHONY: migrate-local
migrate-local:
	@.venv/bin/python manage.py migrate

# Предупреждает, если модель разошлась с миграциями: забытый
# makemigrations означает, что на проде схема не совпадёт с кодом.
.PHONY: check-migrations
check-migrations:
	@.venv/bin/python manage.py makemigrations --check --dry-run

# Деплой: поднимаем весь стек и ждём healthcheck.
#
# Сервис не указываем и --no-deps не ставим намеренно. На первом запуске
# `up -d web --no-deps` не создавал nginx вообще: его нет в списке
# сервисов, а depends_on у него на web, а не наоборот. Сайт оставался
# недоступен при полностью здоровом web.
#
# На последующих деплоях лишнего простоя не будет: compose пересоздаёт
# только то, что действительно изменилось. Образ nginx запинен по
# digest, конфиг неизменен — значит работающий nginx не трогается и
# /static/ с /media/ не простаивают.
#
# Миграции отдельным шагом не делаются: их применяет entrypoint при старте
# контейнера (docker/entrypoint.sh), до запуска gunicorn.
.PHONY: deploy
deploy:
	@${DC} -f ${DC_FILE} pull
	@${DC} -f ${DC_FILE} up -d --wait
	@${DC} -f ${DC_FILE} ps

# Откат: тег плавающий, поэтому возвращаем тег предыдущему локальному образу.
# Список образов с датами — шаг 1, подставьте ID из вывода.
.PHONY: rollback
rollback:
	@echo "1. Найти образ, работавший до деплоя:"
	@${D} images ${IMAGE%:*} --format 'table {{.ID}}\t{{.CreatedAt}}\t{{.Tag}}'
	@echo ""
	@echo "2. Вернуть ему тег (IMAGE_ID из шага 1):"
	@echo "   ${D} tag <IMAGE_ID> ${IMAGE}"
	@echo "3. Перезапустить и проверить:"
	@echo "   ${DC} -f ${DC_FILE} up -d --wait"
	@echo "   make verify"
	@echo ""
	@echo "Если применены миграции, база тоже откатывается из бэкапа:"
	@echo "   4. остановить приложение, вернуть файл бэкапа в db_data, поднять"
	@echo "      (вместе с -wal и -shm, либо после checkpoint)"
	@echo ""
	@echo "Откат проверяется так же, как деплой: make verify"

# Старые цели удалены, но оставлены как заглушки: вызов не должен падать
# с «No rule to make target», а должен подсказывать новое имя.
.PHONY: cash
cash:
	@echo "cash переименована в prune-safe. Запускаю."
	@$(MAKE) prune-safe

# Прежние цели работали через exec внутрь контейнера, где созданный файл
# миграции не переживал пересоздание. Оставлены заглушками, чтобы старый
# вызов подсказывал новое имя.
.PHONY: migrations
migrations:
	@echo "Цель migrations больше не работает: файл миграции, созданный"
	@echo "внутри контейнера, исчезал при пересоздании. Используйте:"
	@echo "  make makemigrations   # создать файл локально"
	@echo "  make migrate-local    # применить к локальной базе"
	@echo "Файл миграции затем нужно закоммитить — без него он не попадёт в образ."

.PHONY: migrate
migrate:
	@echo "На сервере миграции применяет entrypoint при старте контейнера."
	@echo "Вручную запускать не нужно. Локально — make migrate-local."

.PHONY: wait-for-web
wait-for-web:
	@echo "wait-for-web больше не нужна: 'make deploy' ждёт healthcheck сам."

.PHONY: app-rebuild-new-image
app-rebuild-new-image:
	@echo "Цель заменена. Новый порядок:"
	@echo "  1. make test && make app-build && make app-push   # на машине разработчика"
	@echo "  2. make deploy                                   # на сервере"
	@echo "Не запускаю ничего автоматически: шаги разнесены по машинам."

# Проверка деплоя. Сделано отдельной командой не для красоты: первый
# запуск в бою показал, что web может быть полностью здоров, а сайт при
# этом недоступен — не был поднят nginx. И `200` на главной ничего не
# говорит о статике: страница отрендерится, а картинки отдадут 404.
# Поэтому проверяем оба конца отдельно.
.PHONY: verify
verify:
	@echo "=== контейнеры ==="
	@${DC} -f ${DC_FILE} ps
	@echo ""
	@echo "=== приложение отвечает изнутри ==="
	@${DC} -f ${DC_FILE} exec -T ${SERVICE_APP_NAME} \
		curl -s -o /dev/null -w "healthz: %{http_code}\n" http://127.0.0.1:8000/healthz/
	@echo ""
	@echo "=== nginx отвечает снаружи (Host: $(DEPLOY_HOST)) ==="
	@curl -s -o /dev/null -w "через nginx: %{http_code}\n" \
		-H "Host: $(DEPLOY_HOST)" http://127.0.0.1/
	@echo ""
	@echo "=== статика доходит до браузера ==="
	@for u in $$(curl -s -H "Host: $(DEPLOY_HOST)" http://127.0.0.1/login/ \
	           | grep -oE '/static/[^"]+' | sort -u); do \
		printf "%-60s %s\n" "$$u" \
		  "$$(curl -s -o /dev/null -w '%{http_code}' -H "Host: $(DEPLOY_HOST)" \
		      "http://127.0.0.1$$u")"; \
	done
	@echo ""
	@echo "Ожидается: healthz 200, через nginx 302 или 200, все /static/ — 200"
	@echo "Если /static/ дают 404, манифест в шаблоне разошёлся с томом."
	@echo "Если DEPLOY_HOST пуст, задайте DJANGO_ALLOWED_HOSTS в .env"

# Локальный бэкап базы. Снимок делается через backup API модуля sqlite3,
# а не копированием файла: при активном WAL простой cp может поймать
# незакоммиченные страницы. Хранится 7 последних копий.
.PHONY: backup
backup:
	@mkdir -p backups
	@${DC} -f ${DC_FILE} exec -T ${SERVICE_APP_NAME} python -c \
		"import sqlite3, datetime, pathlib; \
		ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S'); \
		dst = pathlib.Path('/app/backups') / ('db-' + ts + '.sqlite3'); \
		src = sqlite3.connect('/app/data/db.sqlite3'); \
		dstc = sqlite3.connect(dst); src.backup(dstc); \
		dstc.close(); src.close(); print('бэкап:', dst.name)"
	@${DC} -f ${DC_FILE} exec -T ${SERVICE_APP_NAME} \
		sh -c 'ls -t /app/backups/db-*.sqlite3 | tail -n +8 | xargs -r rm --'
	@echo "Хранятся 7 последних бэкапов в ./backups"