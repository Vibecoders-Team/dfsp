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
RUN uv venv && \
    . .venv/bin/activate && \
    uv pip install fastapi "uvicorn[standard]" pydantic-settings && \
    uv pip install ruff pytest pyright

# 5) пробрасываем порт и команда запуска uvicorn
EXPOSE 8000
CMD ["/bin/sh", "-lc", ". .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
