# Single image: builds the React UI, then serves it from the FastAPI app.
FROM node:20.18-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-fund --no-audit
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app/backend
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist /app/frontend/dist
ENV KARSAATHI_TODAY=2026-11-16
EXPOSE 8000
CMD ["sh", "-c", "[ -f data/karsaathi.db ] || python -m app.seed; uvicorn app.main:app --host 0.0.0.0 --port 8000"]
