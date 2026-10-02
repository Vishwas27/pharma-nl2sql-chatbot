# ==============================================================================
# Pharma Analytics Bot - Production Docker Container
# ==============================================================================
FROM python:3.10-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8000

WORKDIR /app

# Install system dependencies (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code, schemas, and domain docs
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY schema/ ./schema/
COPY docs/ ./docs/
COPY scripts/ ./scripts/
COPY run.py .
COPY DESIGN.md .

# Pre-build full 2,000,000-row database directly into the container image
RUN python scripts/build_full_database.py

# Expose server port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Launch application
CMD ["python", "run.py"]
