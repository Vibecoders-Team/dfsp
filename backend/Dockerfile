FROM python:3.11-slim

# 1) минимальные системные пакеты
RUN apt-get update && apt-get install -y --no-install-recommends curl libpq-dev gcc && rm -rf /var/lib/apt/lists/*

# 2) ставим uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    /root/.local/bin/uv --version

ENV PATH="/root/.local/bin:${PATH}"

# Устанавливаем рабочую директорию в корень БЕКЕНДА
WORKDIR /app/backend

# 3) копируем весь backend внутрь образа
COPY . /app/backend

# 4) создаём виртуальное окружение и ставим зависимости
# NOTE: libpq-dev и gcc нужны для сборки psycopg/asyncpg
RUN python -m venv /app/.venv \
 && /app/.venv/bin/python -m pip install -U pip \
 && /app/.venv/bin/pip install \
      fastapi "uvicorn[standard]" pydantic-settings \
      sqlalchemy alembic asyncpg psycopg[binary] \
      ruff pytest pyright

# чтобы не "активировать" venv — добавим его в PATH
ENV PATH="/app/.venv/bin:${PATH}"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Стандартная команда запуска будет переопределена в docker-compose
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
