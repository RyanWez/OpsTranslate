# Stage 1: Build Vue 3 Admin Frontend
FROM node:22-alpine AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Python Backend & Final Container
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/app

RUN useradd --create-home --shell /bin/false appuser \
    && apt-get update -qq && apt-get install -y -qq --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app/ ./app/
# Copy fresh compiled frontend assets into app/static/admin
COPY --from=frontend-builder /build/app/static/admin ./app/static/admin
COPY alembic/ ./alembic/
COPY alembic.ini .

RUN mkdir -p /srv/app/data && chown -R appuser:appuser /srv/app
USER appuser

EXPOSE 8000

# Run DB migrations at deploy time (needs DATABASE_URL), then serve.
CMD ["sh", "-c", "if [ -n \"$DATABASE_URL\" ]; then alembic upgrade head && python -m app.store.seed; fi && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
