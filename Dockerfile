FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=cloud_ca \
    if [ -f /run/secrets/cloud_ca ]; then npm_config_cafile=/run/secrets/cloud_ca npm ci; else npm ci; fi
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 APP_ENV=production STATIC_DIR=/app/frontend/dist
WORKDIR /app/backend
COPY backend/requirements.txt ./requirements.txt
RUN --mount=type=secret,id=cloud_ca \
    if [ -f /run/secrets/cloud_ca ]; then PIP_CERT=/run/secrets/cloud_ca pip install --no-cache-dir --require-hashes -r requirements.txt; else pip install --no-cache-dir --require-hashes -r requirements.txt; fi \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home app
COPY --chown=app:app backend/app ./app
COPY --from=frontend --chown=app:app /build/dist /app/frontend/dist
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/health', timeout=3)"
CMD ["sh", "-c", "exec uvicorn app.asgi:app --host 0.0.0.0 --port ${PORT:-8000}"]
