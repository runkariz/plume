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
ENV PLUME_DATA_DIR=/data
WORKDIR /app
COPY --from=build --chown=plume:plume /app /app
USER plume
EXPOSE 18480 18481
HEALTHCHECK --interval=5s --timeout=3s --retries=20 \
  CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:18480/health', timeout=2)" || exit 1
ENTRYPOINT ["plume"]
CMD ["serve", "--host", "0.0.0.0"]
