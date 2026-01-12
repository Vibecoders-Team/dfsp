FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

# system packages for psycopg/asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git libpq-dev gcc \
 && rm -rf /var/lib/apt/lists/*

# install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# dependency files first (layer cache)
COPY pyproject.toml ./
COPY uv.lock ./

# create and sync the environment
# --all-extras will include [project.optional-dependencies].dev when needed
RUN uv sync

ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:${PATH}"

# project code next (dev will be overridden by volume mount)
COPY app/ app/
COPY tests/ tests/
COPY migrations/ migrations/
COPY alembic.ini .
COPY docker/ docker/
RUN chmod +x docker/entrypoint.sh


EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ready || exit 1

# default command (started via compose)
CMD ["bash", "-lc", "./docker/entrypoint.sh api"]
