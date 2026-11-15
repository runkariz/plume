# Plume server image: one image, several commands (serve | mcp | load | migrate | worker).
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv
WORKDIR /app

FROM base AS build
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
RUN useradd --system --uid 10001 --home /app plume \
 && mkdir -p /data && chown plume:plume /data
# Inside a container both servers listen on all interfaces (serve and mcp alike); the defaults
# outside one stay 127.0.0.1.
ENV PLUME_DATA_DIR=/data PLUME_API_HOST=0.0.0.0 PLUME_MCP_HOST=0.0.0.0
WORKDIR /app
COPY --from=build --chown=plume:plume /app /app
USER plume
EXPOSE 18480 18481
# The API (serve, 18480) or the MCP process (mcp, 18481): both answer GET /health.
HEALTHCHECK --interval=5s --timeout=3s --retries=20 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:18480/health', timeout=2)" 2>/dev/null \
   || python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:18481/health', timeout=2)" \
   || exit 1
ENTRYPOINT ["plume"]
CMD ["serve", "--host", "0.0.0.0"]
