# ---- build the web front end
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- application image
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UCF_FRONTEND_DIST=/app/frontend/dist UCF_ATTACHMENT_DIR=/data/attachments
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY migrations ./migrations
COPY scripts ./scripts
COPY configuration ./configuration
COPY alembic.ini .
COPY --from=web /web/dist ./frontend/dist
RUN useradd --create-home --uid 10001 ucfin && mkdir -p /data/attachments && chown -R ucfin /data
USER ucfin
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"
CMD ["sh", "-c", "alembic upgrade head && python -m scripts.seed && uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers ${UCF_WORKERS:-2} --proxy-headers"]
