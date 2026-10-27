# Build from the project root:  docker build -f deploy/Dockerfile -t qe-connect .
FROM node:22-alpine AS web
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 QEC_HOST=0.0.0.0 QEC_PORT=8000 QEC_DATA_DIR=/data
WORKDIR /app
COPY backend/requirements-postgres.lock backend/
RUN pip install --no-cache-dir --require-hashes -r backend/requirements-postgres.lock
COPY backend/app backend/app
COPY --from=web /src/frontend/dist frontend/dist
RUN useradd --system --uid 10001 --home /data qec && mkdir -p /data && chown qec /data
USER qec
WORKDIR /app/backend
EXPOSE 8000
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1
CMD ["python", "-m", "app"]
