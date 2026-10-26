# Imagen única para api y worker (cambia el comando en docker-compose).
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --all-extras --no-install-project
COPY src ./src
COPY effects ./effects
COPY assets ./assets
COPY presets ./presets
COPY web ./web
COPY docs ./docs
RUN uv sync --frozen --no-dev --all-extras
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
