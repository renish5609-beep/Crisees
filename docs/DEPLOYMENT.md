# Deployment

## Live deployment

| Component | URL | Host |
| --- | --- | --- |
| Web app (Next.js) | https://crisees-drea7.vercel.app | Vercel project `crisees`, root `frontend/` (Hobby plan, free) |
| API (FastAPI) | https://crisees-api-drea7.vercel.app | Vercel project `crisees-api`, root `backend/`, Python function (Hobby plan, free) |
| Data release | https://github.com/renish5609-beep/Crisees/releases/tag/data-v1 | GitHub Release `data-v1` |

Both projects deploy automatically from branch `claude/sleepy-cori-ki2xgv`, which is the repository's
default branch. Deployment protection is off so judges can open the app without a Vercel login.

Verified in production on 2026-11-22:

- `/health` returns `regions_with_processed_data: 1` in the `production` environment.
- `/demo` returns all five comparison cases with feasible constraint checks.
- 18 endpoints returned 200.
- CORS allows the app's origin and rejects unknown origins.
- `npm run e2e` passes against both live URLs (see RELEASE_CHECKLIST.md).

**Cost.** No paid services are used. Render was evaluated, but it requires a payment method, so it was not
created.

## How the API fits on Vercel

Vercel's standard Python function size is **250 MB uncompressed**. Above that, dependencies are installed
at runtime into `/tmp`, which fails for this stack. The API's geospatial dependencies total about 550 MB,
so the backend build does the following:

1. **Lean core dependencies.** `backend/pyproject.toml` core dependencies are only what the API imports.
   The pipeline extras (OSMnx, pyogrio, requests) and the `server` extra (uvicorn) are separate. Docker
   and local development install `.[dev]`, or `.[pipeline,server]` for Docker.
2. **Build hook.** `backend/vercel_build.py` runs via `[tool.vercel.scripts] build`, after dependencies
   are installed. It only acts when `VERCEL=1`, and only on `.vercel/python/.venv`.
   - It downloads the data release from `CRISEES_DATA_URL` and verifies `CRISEES_DATA_SHA256`; on a
     mismatch the build fails.
   - It reads each dataset with pyarrow, which is lossless, converts Arrow-backed strings and labels to
     plain Python objects, refuses any pickle that still references pyarrow, and writes gzip pickles to
     `backend/data_bundle/processed/<region>/` (18.7 MB).
   - It removes pyarrow, pyogrio, unused scipy subpackages and test suites from the virtualenv. In the
     local rehearsal this took the packages from 398 MB to 239 MB.
3. **Runtime.** `CRISEES_DATA_DIR=data_bundle`. The repository loads `.pkl.gz` files when present and
   Parquet otherwise, so local and Docker behaviour are unchanged. A rehearsal with pyarrow imports
   blocked returned 200 from every endpoint, with identical demo numbers.

API environment variables (project `crisees-api`, Production and Preview):

| Variable | Value |
| --- | --- |
| `CRISEES_ENV` | `production` |
| `CRISEES_DATA_DIR` | `data_bundle` |
| `CRISEES_DATA_URL` | `https://github.com/renish5609-beep/Crisees/releases/download/data-v1/crisees-data-houston-sw-pilot-20261122T002055Z.tar.gz` |
| `CRISEES_DATA_SHA256` | `0fe0e8e3d03c2f3a66b03c6917c6f48ceb348d455a3404da0e7d7e018ebc69eb` |
| `CRISEES_CORS_ORIGINS` | `https://crisees-drea7.vercel.app,http://localhost:3000` |
| `CRISEES_CORS_ORIGIN_REGEX` | `^https://crisees[a-z0-9-]*\.vercel\.app$` (preview URLs) |

Frontend environment variables (project `crisees`):

| Variable | Value |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | `https://crisees-api-drea7.vercel.app` |
| `NEXT_PUBLIC_DEFAULT_REGION` | `houston-sw-pilot` |
| `NEXT_PUBLIC_BASEMAP_TILES` | `none`. External raster tiles are opt-in: CARTO's free tiles now require an API key and rendered "API KEY REQUIRED" in production. The map uses its self-hosted major-roads layer for context |

**Cold starts.** After idle periods the first request starts a new function instance, which loads the
bundled data and builds the routing engine. The first `/demo` takes about 10–12 s. Later requests on a
warm instance are served from the cache in milliseconds. Before presenting, open the app once to warm it.

## Data release (immutable, checksummed)

Processed data is Git-ignored. Release `data-v1` holds:

- `crisees-data-houston-sw-pilot-20261122T002055Z.tar.gz`: 22,107,830 bytes, SHA-256
  `0fe0e8e3d03c2f3a66b03c6917c6f48ceb348d455a3404da0e7d7e018ebc69eb`. It contains processed datasets
  and `ATTRIBUTION.md`, with the ODbL and CDLA notices.
- The matching `.sha256` file.

Both assets were verified publicly downloadable, and the checksum was independently recomputed.

For a new data version, run `python scripts/package_data_release.py`, publish a new release tag, and
update `CRISEES_DATA_URL` and `CRISEES_DATA_SHA256`. The next deployment bundles the new data.

## Redeploying

Push to `claude/sleepy-cori-ki2xgv`. Both Vercel projects build automatically: about 1 minute for the
frontend and 1–2 minutes for the API.

## Alternative: Docker host (Render, Fly.io, Cloud Run)

`backend/Dockerfile`, `backend/docker-entrypoint.sh` and `render.yaml` remain available for a
long-running server (about 1 GB RAM). The entrypoint fetches and verifies the same release at start.
Render's Standard plan costs about $25/month plus disk; it was not used. See the git history for the
earlier Render instructions.

## Verifying a deployment

```bash
curl https://crisees-api-drea7.vercel.app/health
```
```bash
curl https://crisees-api-drea7.vercel.app/api/v1/regions/houston-sw-pilot/demo | jq '.result.cases[] | {case, served: .totals.served}'
```
```bash
cd frontend && APP_URL=https://crisees-drea7.vercel.app API_URL=https://crisees-api-drea7.vercel.app npm run e2e
```

Node's built-in `fetch` ignores proxy variables; behind a proxy, add `NODE_USE_ENV_PROXY=1`.
