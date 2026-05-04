# Gemeinsames Image für Backend und Worker
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System-Pakete:
# - build-essential / libxml2-dev / libxslt-dev: lxml-Build
# - libpango-1.0-0, libpangoft2-1.0-0, libharfbuzz0b, libcairo2,
#   libgdk-pixbuf-2.0-0, fontconfig, shared-mime-info: WeasyPrint
#   braucht GTK-Stack zur Laufzeit für PDF-Rendering
# - fonts-dejavu-core: ohne Font fallback rendert Text in Tofu/Squares
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libxml2-dev \
        libxslt-dev \
        curl \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        fontconfig \
        shared-mime-info \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Dependencies separat installieren (besseres Layer-Caching)
COPY pyproject.toml ./
RUN pip install --upgrade pip && \
    pip install -e '.[dev]'

# App-Code
COPY . .

EXPOSE 8000

# Default-Command wird in docker-compose überschrieben
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
