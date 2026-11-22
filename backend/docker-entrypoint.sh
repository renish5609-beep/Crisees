#!/bin/sh
# Provision data (if needed), then start the API.
#  1. Data already present (baked into the image or on a persistent disk): use it.
#  2. CRISEES_DATA_URL + CRISEES_DATA_SHA256: fetch the checksum-verified release.
#  3. CRISEES_BUILD_DATA=1: rebuild from public sources (slow, ~5 min, needs ~2 GB RAM;
#     pin CRISEES_OVERTURE_RELEASE and providers for reproducibility).
#  4. Otherwise start anyway: /health reports no data and data endpoints return
#     503 dataset_not_available with instructions. Nothing is fabricated.
set -e
cd "${APP_DIR:-/app}"
REGION="${CRISEES_REGION:-houston-sw-pilot}"
MANIFEST="$CRISEES_DATA_DIR/processed/$REGION/manifest.json"

if [ -n "$CRISEES_DATA_URL" ]; then
  python scripts/fetch_data_release.py --region "$REGION" || echo "WARNING: data release fetch failed; continuing with whatever data exists"
elif [ ! -f "$MANIFEST" ] && [ "${CRISEES_BUILD_DATA:-0}" = "1" ]; then
  python scripts/download_data.py --region "$REGION" --road-provider "${CRISEES_ROAD_PROVIDER:-overture}" \
    --facility-provider "${CRISEES_FACILITY_PROVIDER:-overture}" --flood-provider "${CRISEES_FLOOD_PROVIDER:-auto}" || true
  python scripts/process_data.py --region "$REGION" || true
fi
[ -f "$MANIFEST" ] || echo "WARNING: no processed data for $REGION; API will return 503 for data endpoints."

# Warm the analysis engine in the background so the first visitor does not pay the cold start.
( sleep 3; python - <<'PY' || true
import os, urllib.request, json
port = os.environ.get("PORT", "8000")
base = f"http://127.0.0.1:{port}/api/v1/regions/{os.environ.get('CRISEES_REGION', 'houston-sw-pilot')}"
for path, body in [("/scenarios/evaluate", {"scenario": "severe"}), ("/demo", None)]:
    try:
        req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body else None,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=300).read()
    except Exception as exc:  # noqa: BLE001
        print("warmup skipped:", exc)
PY
) &

# One worker: the engine caches ~1 GB of graph and results per process.
exec uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --proxy-headers --timeout-keep-alive 75
