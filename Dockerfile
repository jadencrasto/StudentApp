# ==============================================================================
# SAIS Production Dockerfile (Single Container: React Frontend + FastAPI Backend)
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Build Frontend Assets
# ------------------------------------------------------------------------------
FROM node:20-alpine AS frontend-builder
WORKDIR /build

# Ensure Playwright never downloads browser binaries during container build
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

# Copy dependency manifests first to leverage layer caching
COPY frontend/package*.json ./
RUN npm ci

# Copy frontend source files and build production static bundle
COPY frontend/ ./
RUN npm run build

# ------------------------------------------------------------------------------
# Stage 2: Production Python Runtime
# ------------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

WORKDIR /app

# Install minimal OS dependencies:
# - tesseract-ocr: Fallback text recognition for scans/images
# - libgl1, libglib2.0-0: Graphic/image dependencies for PyMuPDF & OpenCV
# - tzdata: ZoneInfo timezone database (/usr/share/zoneinfo) for Asia/Kolkata
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root application user
RUN groupadd -g 10001 sais && \
    useradd -u 10001 -g sais -s /bin/sh -m appuser

# Install Python dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ /app/backend/

# Copy built frontend distribution from stage 1
COPY --from=frontend-builder /build/dist /app/frontend/dist

# Set up local uploads scratch directory and permissions
RUN mkdir -p /app/backend/uploads && \
    chown -R appuser:sais /app

# Drop root privileges
USER appuser

# Configure environment defaults
ENV PORT=8000 \
    PYTHONPATH=/app/backend \
    FRONTEND_DIST_DIR=/app/frontend/dist \
    PYTHONUNBUFFERED=1

EXPOSE 8000

WORKDIR /app/backend

# Single Uvicorn worker bound to $PORT injected by Render (free tier 512MB RAM constraint)
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]

