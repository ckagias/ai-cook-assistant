# The app on Cloud Run (or any container host): one HTTP port, TLS by the platform.
# Built from backend/ with only what .gcloudignore lets through - never .env, certs or venvs.
# Detection is left out (its models need far more memory); the app runs without it.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run sets PORT. Proxy headers: the client's own address, for the per-IP rate limits.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips="*"
