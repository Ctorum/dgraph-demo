FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY app ./app

EXPOSE 8000

ENTRYPOINT ["uv", "run", "--no-sync", "python", "-m", "app.main"]
