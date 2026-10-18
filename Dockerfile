# MeterZero on Cloud Run: one container serving the API and the React + Three.js app.

# 1. Build the frontend
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 2. The backend (API + engine) and the built frontend. The demo plant is trained at build time,
#    so containers start in seconds. The Gemini key comes from Cloud Run (Secret Manager), never the image.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/meterzero ./meterzero
COPY backend/server ./server
COPY backend/samples ./samples
COPY --from=frontend /frontend/dist ./static
RUN python -m meterzero all

# Cloud Run sets $PORT (8080 by default).
CMD uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-8080}
