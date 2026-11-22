# Release checklist (final submission)

Checked items were verified on 2026-11-22. Unchecked items have not been verified or are pending your
action.

## Code and tests

- [x] `cd backend && python -m pytest`: 157 passed (real-data tests ran against the local processed data)
- [x] `cd frontend && npm run typecheck && npm run lint && npm test`: pass (11 unit tests)
- [x] `NEXT_PUBLIC_API_BASE_URL=https://crisees-api-drea7.vercel.app npm run build` succeeds (first load for `/` is 135 kB)
- [x] `python scripts/validate_data.py`: 12/12 datasets valid (local data and the installed release)
- [x] `APP_URL=https://crisees-drea7.vercel.app API_URL=https://crisees-api-drea7.vercel.app npm run e2e` passes, with no console errors
- [x] Branch `claude/sleepy-cori-ki2xgv` pushed
- [x] GitHub Actions CI green on the last code change `c83035d` (run 13). Runs 11–12 failed on the e2e-script lint issue that this commit fixed; later docs-only commits rerun the same checks

## Data release

- [x] Release `data-v1` published with both assets: https://github.com/renish5609-beep/Crisees/releases/tag/data-v1
- [x] Archive publicly downloadable; SHA-256 recomputed and matches `0fe0e8e3…69eb`
- [x] `CRISEES_DATA_SHA256` on the API equals the published `.sha256`
- [x] `ATTRIBUTION.md` present in the artifact (ODbL / CDLA notices)

## Deployment

- [x] API `/health` returns `regions_with_processed_data: 1` (https://crisees-api-drea7.vercel.app/health)
- [x] API `/demo` returns 5 cases, all `constraint_check_feasible: true`; values match the Phase 2 reference (5,214 → 9,493 of 23,033)
- [x] Frontend `NEXT_PUBLIC_API_BASE_URL` points at the production API (no localhost)
- [x] API CORS allows https://crisees-drea7.vercel.app and rejects unknown origins
- [x] Live status pill reads "API connected"
- [x] Guided demo completes all 8 steps on the live site (automated)
- [x] Mobile at 390 px: no horizontal scroll (automated)
- [x] No paid services activated

## Content honesty

- [x] Displayed numbers come from live API responses (e2e compares the UI against direct API calls)
- [x] Disclaimer visible: Overview, rail, Methodology, Impact
- [x] "No FEMA data" hatching visible and explained in the legend
- [x] Equity vs equal described as redistribution when totals are equal ("no change" shown)
- [x] Hub details show the authorization warning for schools and private property
- [x] Devpost draft claims no users, partners or real-world impact

## Submission (your action)

- [ ] Demo video (≤ 3 min) recorded from `docs/DEMO_SCRIPT.md`. **Pending: you are recording this**
- [ ] Devpost fields filled from `docs/DEVPOST_SUBMISSION.md`, with the video link added
- [ ] Screenshots attached from `docs/img/` (real production captures)
- [ ] Final Devpost submission. **Pending your approval and action**
