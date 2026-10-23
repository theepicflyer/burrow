FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS python-build-stage

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY uv.lock pyproject.toml ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# The frontend bundle, translations and static files are the same on every
# architecture, so they are built once on the build host's platform instead of
# under QEMU for each target.
FROM --platform=$BUILDPLATFORM node:lts-alpine AS vite_build
WORKDIR /usr/src/frontend

COPY ./frontend/package.json ./frontend/package-lock.json* ./

RUN --mount=type=cache,target=/root/.npm \
    npm ci || npm install

COPY ./frontend .
COPY ./app/templates /usr/src/app/templates

RUN npm run build

# Same first steps as python-build-stage, so a build-host-native target reuses them.
FROM --platform=$BUILDPLATFORM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS static_build

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY uv.lock pyproject.toml ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

RUN apt-get update && apt-get install --no-install-recommends -y gettext \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /usr/src/app

COPY --from=vite_build /usr/src/frontend/build /usr/src/frontend/build
COPY ./app .

RUN python manage.py compilemessages --settings "WYGIWYH.settings" && \
    python manage.py collectstatic --noinput

FROM python:3.11-slim-bookworm AS python-run-stage

WORKDIR /usr/src/app

RUN addgroup --system app && \
    adduser --system --ingroup app app && \
    chown app:app /usr/src/app && \
    mkdir /temp && \
    chown app:app /temp

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Install runtime dependencies
RUN --mount=type=cache,target=/root/.cache/apt \
    apt-get update && \
    apt-get install --no-install-recommends -y gettext supervisor libpq5 && \
    rm -rf /var/lib/apt/lists/*

COPY --chown=app:app ./docker/prod/django/start /start
COPY --chown=app:app ./docker/prod/procrastinate/start /start-procrastinate
COPY --chown=app:app ./docker/prod/supervisord/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY --chown=app:app ./docker/prod/supervisord/supervisord.conf /etc/supervisord.conf
COPY --chown=app:app ./docker/prod/supervisord/start /start-single

RUN sed -i 's/\r$//g' /start && \
    chmod +x /start && \
    sed -i 's/\r$//g' /start-procrastinate && \
    chmod +x /start-procrastinate && \
    sed -i 's/\r$//g' /start-single && \
    chmod +x /start-single

COPY --from=python-build-stage /app/.venv /app/.venv
COPY --from=vite_build --chown=app:app /usr/src/frontend/build /usr/src/frontend/build
COPY --from=static_build --chown=app:app /usr/src/app .

# Last, because it changes on every build and invalidates every layer after it.
ARG VERSION=dev
ENV APP_VERSION=$VERSION

USER app

CMD ["/start-single"]
