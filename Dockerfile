FROM ghcr.io/astral-sh/uv:0.12.19 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend backend
COPY frontend frontend
COPY alembic.ini ./
RUN useradd --uid 10001 --create-home app
USER 10001
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log", "--no-proxy-headers"]
