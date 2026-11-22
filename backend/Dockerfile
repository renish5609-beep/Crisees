# Crisees API. Build from the repository root:
#   docker build -f backend/Dockerfile -t crisees-api .
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CRISEES_DATA_DIR=/data \
    PORT=8000

WORKDIR /app
# All geospatial deps ship manylinux wheels (GDAL via pyogrio, GEOS via shapely, PROJ via pyproj, HiGHS via scipy).
COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/app backend/app
COPY backend/pipeline backend/pipeline
RUN pip install --upgrade pip && pip install "./backend[pipeline,server]"
COPY scripts scripts
COPY backend/docker-entrypoint.sh /usr/local/bin/crisees-entrypoint
RUN chmod +x /usr/local/bin/crisees-entrypoint && mkdir -p /data && useradd --create-home --uid 10001 crisees \
    && chown -R crisees /data /app
USER crisees

# Optional: bake data into the image at build time (otherwise provisioned at start).
ARG CRISEES_DATA_URL=""
ARG CRISEES_DATA_SHA256=""
RUN if [ -n "$CRISEES_DATA_URL" ]; then cd /app && python scripts/fetch_data_release.py --url "$CRISEES_DATA_URL" --sha256 "$CRISEES_DATA_SHA256"; fi

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health',timeout=4)"
ENTRYPOINT ["crisees-entrypoint"]
