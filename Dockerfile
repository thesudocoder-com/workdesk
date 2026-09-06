FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev

VOLUME ["/data"]
EXPOSE 8010
CMD ["sh", "-c", "uv run alembic upgrade head && exec uv run uvicorn Application.Main:app --host 0.0.0.0 --port 8010 --workers 1"]
