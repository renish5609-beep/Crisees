# Deployment

Target: the frontend on **Vercel** (Next.js) and the API on **Render** (Docker). Any Docker host with about
1 GB of RAM works for the API.

**Status:** deployment configurations are complete and were tested locally: the entrypoint, data
provisioning, CORS and the production frontend build. A live public deployment has **not** been verified.
The build environment had no Render (or other container host) credentials, no Docker daemon, and no
permission to create GitHub Release assets. The steps below are what remains.

## 1. Publish the data release (once per data version)

Processed data (about 27 MB) is Git-ignored. Build an immutable, checksummed artifact:

```bash
python scripts/package_data_release.py --region houston-sw-pilot
```

This produces `dist/crisees-data-houston-sw-pilot-<stamp>.tar.gz` and its `.sha256` file. The artifact
contains processed data plus `ATTRIBUTION.md`, which covers ODbL for the OSM-derived road tables and
CDLA-Permissive-2.0 for Overture places.

Artifact built in this environment:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `crisees-data-houston-sw-pilot-20261122T002055Z.tar.gz` | 22,107,830 | `0fe0e8e3d03c2f3a66b03c6917c6f48ceb348d455a3404da0e7d7e018ebc69eb` |

Upload it as a GitHub Release asset (immutable, public):

```bash
gh release create data-v1 dist/crisees-data-houston-sw-pilot-*.tar.gz dist/*.sha256 \
  --repo renish5609-beep/Crisees --title "Crisees data v1 (houston-sw-pilot)" \
  --notes "Processed datasets for the Crisees API. See ATTRIBUTION.md inside."
```

The asset URL has this form:
`https://github.com/renish5609-beep/Crisees/releases/download/data-v1/crisees-data-houston-sw-pilot-20261122T002055Z.tar.gz`

## 2. Deploy the API on Render

1. Render dashboard → **New → Blueprint** → select this repository and branch. `render.yaml` defines
   `crisees-api`: a Docker service on the `standard` plan (2 GB), a health check on `/health`, and a 1 GB
   disk at `/data`.
2. Set the environment variables:

   | Variable | Value |
   | --- | --- |
   | `CRISEES_DATA_URL` | The release asset URL from step 1 |
   | `CRISEES_DATA_SHA256` | `0fe0e8e3d03c2f3a66b03c6917c6f48ceb348d455a3404da0e7d7e018ebc69eb` |
   | `CRISEES_CORS_ORIGINS` | `https://<your-vercel-domain>` (comma-separated list allowed) |
   | `CRISEES_CORS_ORIGIN_REGEX` | Optional, for previews, e.g. `^https://crisees-.*\.vercel\.app$` |

3. Deploy. The entrypoint (`backend/docker-entrypoint.sh`) then does the following:
   - It downloads the release, verifies the SHA-256 and refuses to install on a mismatch. It extracts
     atomically, then validates all 12 datasets. On a persistent disk, a re-run with the same checksum is
     a no-op.
   - It starts uvicorn with one worker. The engine caches the road graph, about 1 GB per process.
   - It warms the engine in the background (the severe scenario and the demo), so the first visitor gets
     cached answers.
4. Verify: `curl https://<api>/health` should return `"regions_with_processed_data": 1`.
   `curl https://<api>/api/v1/regions/houston-sw-pilot/demo` should return the five comparison cases.

**Fallbacks.**

- If `CRISEES_DATA_URL` is unset and `CRISEES_BUILD_DATA=1`, the container rebuilds data from public
  sources. This takes about 5 minutes and needs about 2 GB RAM. Pin `CRISEES_OVERTURE_RELEASE=2026-11-18.0`
  for reproducibility. Overture removes old releases after a few months, and official FEMA and CDC sources
  may yield *more complete* data than the documented build, so the numbers may differ.
- With no data at all, the API still starts. `/health` reports `regions_with_processed_data: 0` and the
  data endpoints return 503 `dataset_not_available` with instructions. The frontend shows
  "API up, data not provisioned".

**Robustness.**

- **Container restarts:** the disk keeps the data, and the checksum marker skips re-download.
- **Cold start:** about 4 s to build the engine, absorbed by the warm-up.
- **Solver limits:** each solve is time-limited to 30 s by default and 120 s at most, and at most 2
  analysis jobs run concurrently (otherwise 503 `engine_busy`).
- **Caching:** results are LRU-cached by request hash.

Without Docker, you can run the image's steps directly:

```bash
pip install ./backend && python scripts/fetch_data_release.py && uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT
```

**Memory note:** Render's free and starter plans (512 MB) are too small. The process uses about 1 GB once
warm, so choose `standard` or larger.

## 3. Deploy the frontend on Vercel

1. Vercel → **Add New → Project** → import `renish5609-beep/Crisees`. Set **Root Directory** to
   `frontend`. The framework (Next.js) is auto-detected.
2. Environment variables (Production and Preview):

   | Variable | Value |
   | --- | --- |
   | `NEXT_PUBLIC_API_BASE_URL` | `https://<your-render-service>.onrender.com` (no trailing slash; **required**) |
   | `NEXT_PUBLIC_DEFAULT_REGION` | `houston-sw-pilot` |
   | `NEXT_PUBLIC_BASEMAP_TILES` | Optional; default CARTO dark (no labels). Check the tile provider's terms for your traffic |

   Without `NEXT_PUBLIC_API_BASE_URL`, a production build shows a clear "not configured" error. It never
   falls back to localhost.
3. Deploy, then add the Vercel domain to `CRISEES_CORS_ORIGINS` on Render and redeploy the API.
4. Verify:
   - Open the site. The status pill reads "API connected".
   - **Run guided demo** completes all 8 steps.
   - Optional: `APP_URL=https://<vercel> API_URL=https://<api> npm run e2e` from `frontend/`.

## 4. Alternative hosts

- **Fly.io / Railway / Google Cloud Run:** use `backend/Dockerfile` with the same environment variables
  and at least 1 GB of memory. On Cloud Run, set `--memory 2Gi --cpu 2 --concurrency 4`, and either set
  min-instances to 1 or accept cold starts of about 10 s, including the data download.
- **Bake data into the image:** pass `--build-arg CRISEES_DATA_URL=… --build-arg CRISEES_DATA_SHA256=…`.

## Secrets

None are required. The Census API key is optional and unused in deployment. Do not commit `.env` files.
