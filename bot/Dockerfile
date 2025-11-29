FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Install dependencies first for better caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# App sources
COPY app ./app

ENV PYTHONUNBUFFERED=1
EXPOSE 8080 8001

CMD ["uv", "run", "python", "-m", "app.main"]
