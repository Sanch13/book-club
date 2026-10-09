# Синтаксис приложения, дизайн и тексты меняются часто, а зависимости — почти
# никогда. Поэтому код и зависимости копируются разными слоями: правка шаблона
# пересобирает только финальный слой и не тянет заново wheels Pillow.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project --frozen


FROM python:3.13-slim AS runtime

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        libjpeg62-turbo \
        zlib1g \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY manage.py ./
COPY src ./src
COPY templates ./templates
COPY static ./static
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Приложение работает не от root: чтобы даже скомпрометированный процесс
# не писал в системные каталоги.
RUN groupadd -g 1000 miran \
    && useradd -u 1000 -g 1000 -m miran \
    && mkdir -p /app/media /app/data /app/staticfiles \
    && chown -R miran:miran /app

USER miran

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz/ || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

