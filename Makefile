# makefile
DC = docker compose
D = docker
EXEC = docker exec -it
LOGS = docker logs
ENV = --env-file .env
DC_FILE = docker-compose.yml
APP_CONTAINER = web
SERVICE_APP_NAME = web
SERVICE_NGINX_NAME = nginx
IMAGE = miran2025/book-club:0.0.1

.PHONY: app
app:
	@$(MAKE) app-sync
	@${DC} -f ${DC_FILE} up --build -d

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
	@$(MAKE) app-del
	@$(MAKE) cash
	@$(MAKE) app-build
	@$(MAKE) app-push

.PHONY: app-del
app-del:
	@if ${D} image inspect ${IMAGE} >/dev/null 2>&1; then \
		${D} rmi ${IMAGE}; \
	fi

.PHONY: cash
cash:
	@${D} system prune -f

.PHONY: app-rebuild-new-image
app-rebuild-new-image:
	@$(MAKE) app-down
	@$(MAKE) app-del
	@$(MAKE) cash
	@$(MAKE) app
	@$(MAKE) wait-for-web
	@$(MAKE) migrations
	@$(MAKE) migrate

.PHONY: migrations
migrations:
	@${DC} -f ${DC_FILE} exec ${SERVICE_APP_NAME} python manage.py makemigrations

.PHONY: migrate
migrate:
	@${DC} -f ${DC_FILE} exec ${SERVICE_APP_NAME} python manage.py migrate

.PHONY: wait-for-web
wait-for-web:
	@echo "Waiting for web container to be ready..."
	@while ! ${DC} -f ${DC_FILE} exec ${SERVICE_APP_NAME} echo "ready" 2>/dev/null; do \
		sleep 1; \
	done
	@sleep 1
