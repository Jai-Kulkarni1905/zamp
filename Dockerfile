# One container: FastAPI serves the API and the built React app (PLAN.md section 1).

# ---- 1. Build the frontend -------------------------------------------------------------------
FROM node:24-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. Python runtime ------------------------------------------------------------------------
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/ backend/
COPY data/seed/ data/seed/
COPY data/fixtures/ data/fixtures/
COPY data/invoices/ data/invoices/
COPY --from=web /web/dist/ frontend/dist/

# Live mode saves new extractions as fixtures; the app user needs to write there.
RUN chown -R app:app /app/data
USER app

WORKDIR /app/backend
EXPOSE 8000
# Render (and most hosts) pass the port in $PORT. Proxy headers so URLs and client IPs are right behind the host's proxy.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*'"]
