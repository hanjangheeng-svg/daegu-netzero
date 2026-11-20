# Render Docker web service: single-origin React + FastAPI, no external LLM
FROM node:22-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY data ./data
COPY *.py ./
COPY --from=frontend /build/frontend/dist ./frontend/dist
ENV PORT=10000
CMD ["sh", "-c", "python -m uvicorn backend.api:app --host 0.0.0.0 --port ${PORT:-10000}"]
