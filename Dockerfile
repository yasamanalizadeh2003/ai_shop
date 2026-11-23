FROM node:22-slim AS assets
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY static ./static
COPY templates ./templates
COPY apps ./apps
RUN npm run build:css

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
COPY --from=assets /build/static/css/app.css ./static/css/app.css

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
