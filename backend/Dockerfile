# ============================================================
# ◈ Hunt — Backend Dockerfile
# Python 3.12 + Playwright (Chromium) for web scraping
# ============================================================

FROM python:3.12-slim AS base

# Prevent Python from writing .pyc and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps for Playwright/Chromium + general utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Playwright Chromium dependencies
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 libxshmfence1 \
    # General
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium browser
RUN playwright install chromium --with-deps

# Copy application code
COPY . .

# Create output directory
RUN mkdir -p /app/output

# Expose FastAPI port
EXPOSE 8000

# Default: run the chat API server
CMD ["uvicorn", "chat_server:app", "--host", "0.0.0.0", "--port", "8000"]
