# Use a slim Python 3.13 image with uv pre-installed
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /app

# Copy dependencies structure
COPY pyproject.toml /app/

# Install dependencies (exclude dev group, compile bytecode)
RUN uv sync --frozen --no-install-project --no-dev

# Final Production Stage
FROM python:3.13-slim-bookworm

WORKDIR /app

# Copy virtualenv from builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy source code
COPY src/ /app/src/

# Create persistent data volume path for SQLite
RUN mkdir -p /app/data

# Environment configuration
ENV ENV=production
ENV DB_PATH=/app/data/skydeal.db
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "src.main"]
