# syntax=docker/dockerfile:1
# Stage 1: Build Python wheel
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN pip install --no-cache-dir hatchling==1.24.2

# Copy project definition first for layer caching
COPY pyproject.toml README.md LICENSE ./
COPY infersight/ ./infersight/

# Build wheel
RUN pip wheel --no-deps --wheel-dir /build/dist .

# Stage 2: Runtime image
FROM python:3.11-slim AS runtime

ARG INFERSIGHT_VERSION=0.1.0

# Security: run as non-root
RUN groupadd --gid 1001 infersight && \
    useradd --uid 1001 --gid 1001 --no-create-home infersight

WORKDIR /app

# Install runtime wheel
COPY --from=builder /build/dist/*.whl ./
RUN pip install --no-cache-dir *.whl && rm -f *.whl

# Copy pre-built frontend (populated in CI before docker build)
# Falls back gracefully if ui/dist doesn't exist yet
COPY ui/dist/ /app/static/ 2>/dev/null || mkdir -p /app/static

# Runtime configuration
ENV INFERSIGHT_VERSION=${INFERSIGHT_VERSION} \
    INFERSIGHT_SERVER__HOST=0.0.0.0 \
    INFERSIGHT_SERVER__PORT=8000 \
    INFERSIGHT_STORAGE__SQLITE__PATH=/data/infersight.db

# Data volume for SQLite persistence
VOLUME ["/data"]

# Non-root user
USER infersight

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["python", "-m", "infersight"]
CMD ["serve"]
