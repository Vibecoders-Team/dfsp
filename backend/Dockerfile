FROM python:3.11-slim

# 1) минимальные системные пакеты
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# 2) ставим uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    /root/.local/bin/uv --version

ENV PATH="/root/.local/bin:${PATH}"
WORKDIR /app

# 3) копируем весь backend внутрь образа
COPY . /app

# 4) создаём виртуальное окружение и ставим зависимости
RUN python -m venv /app/.venv \
 && /app/.venv/bin/python -m pip install -U pip \
 && /app/.venv/bin/pip install \
      fastapi "uvicorn[standard]" pydantic-settings \
      sqlalchemy alembic asyncpg psycopg[binary] \
      ruff pytest pyright

# чтобы не "активировать" venv — добавим его в PATH
ENV PATH="/app/.venv/bin:${PATH}"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# стандартный старт без ". .venv/bin/activate"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
