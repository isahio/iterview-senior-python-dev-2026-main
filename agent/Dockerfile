FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy workspace manifests and lockfile first for layer caching
COPY pyproject.toml uv.lock ./
COPY agent/ ./agent/
COPY core/ ./core/

RUN uv sync --frozen --no-dev --package ticket-triage-agent

EXPOSE 8000

CMD ["uv", "run", "--package", "ticket-triage-agent", "python", "-m", "app", "--host", "0.0.0.0", "--port", "8000"]
