FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy workspace manifests and lockfile first for layer caching
COPY pyproject.toml uv.lock ./
COPY mcp_server/pyproject.toml ./mcp_server/
COPY mcp_server/app/ ./mcp_server/app/

RUN uv sync --frozen --no-dev --package mcp-server

EXPOSE 8001

CMD ["uv", "run", "--package", "mcp-server", "python", "-m", "app.main"]
