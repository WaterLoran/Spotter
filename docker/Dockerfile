# Single image: Vue build → Flask static + API (gunicorn).
# 不显式指定 # syntax=docker/dockerfile:1，避免 BuildKit 额外拉取前端镜像（部分镜像源失效会直接导致构建失败）。

FROM node:20-alpine AS frontend-build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=5000 \
    DATA_DIR=/data \
    SQLEYE_DB_PATH=/data/sqleye.db

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ARG APT_MIRROR=deb.debian.org

RUN sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && \
    if [ -n "$PIP_TRUSTED_HOST" ]; then \
      pip install -i "$PIP_INDEX_URL" --trusted-host "$PIP_TRUSTED_HOST" -r /app/requirements.txt gunicorn; \
    else \
      pip install -i "$PIP_INDEX_URL" -r /app/requirements.txt gunicorn; \
    fi

COPY backend/ /app/
COPY --from=frontend-build /src/frontend/dist /app/static

RUN mkdir -p /data /app/logs

EXPOSE 5000
VOLUME ["/data"]

# Single worker: one background log scheduler + shared SQLite WAL; multiple workers each ran a scheduler and increased lock contention.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "120", "app:app"]
