FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

# системные пакеты для psycopg/asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git libpq-dev gcc \
 && rm -rf /var/lib/apt/lists/*

# ставим uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# сначала — файлы зависимостей (кэш слоёв)
COPY pyproject.toml ./
# если есть lock — добавьте строку ниже (и в репозиторий):
# COPY uv.lock ./

# создаём и синхронизируем окружение
# --all-extras подтянет [project.optional-dependencies].dev когда понадобятся
RUN uv sync

ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:${PATH}"


# затем — код проекта (в dev будет перекрыт volume-монтом)
COPY app/ app/
COPY migrations/ migrations/
COPY alembic.ini .
COPY docker/ docker/
RUN chmod +x docker/entrypoint.sh


EXPOSE 8000

# команда по умолчанию — запускается через compose
CMD ["bash", "-lc", "./docker/entrypoint.sh api"]
