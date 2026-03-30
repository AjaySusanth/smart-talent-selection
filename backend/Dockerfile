FROM python:3.11-slim AS base
WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN apt-get update && apt-get install -y libmagic1 && rm -rf /var/lib/apt/lists/*

# Copy lockfile and install dependencies
# uv sync is significantly faster than pip install
COPY pyproject.toml requirements.lock ./
RUN uv pip install --system --no-cache -r requirements.lock

FROM base AS development
COPY . .

FROM base AS production
COPY . .
RUN useradd -m appuser && chown -R appuser /app
USER appuser
