# Release checklist (final submission)

## Code and tests

- [ ] `cd backend && python -m pytest` passes (157 tests; real-data tests run when data is present)
- [ ] `cd frontend && npm run typecheck && npm run lint && npm test` passes
- [ ] `NEXT_PUBLIC_API_BASE_URL=<api> npm run build` succeeds
- [ ] `python scripts/validate_data.py`: 12/12 datasets valid
- [ ] `APP_URL=… API_URL=… npm run e2e` passes against the deployed URLs, with no console errors
- [ ] Branch pushed; CI green

## Data release

- [ ] `python scripts/package_data_release.py` run, and the `.tar.gz` and `.sha256` uploaded to a GitHub Release
- [ ] `CRISEES_DATA_SHA256` on the API equals the published `.sha256`
- [ ] `ATTRIBUTION.md` present in the artifact (ODbL / CDLA notices)

## Deployment

- [ ] API `/health` returns `regions_with_processed_data: 1`
- [ ] API `/api/v1/regions/houston-sw-pilot/demo` returns 5 cases, all `constraint_check_feasible: true`
- [ ] Frontend env `NEXT_PUBLIC_API_BASE_URL` points at the API (no localhost)
- [ ] API `CRISEES_CORS_ORIGINS` contains the frontend domain
- [ ] The status pill on the live site reads "API connected"
- [ ] Guided demo completes all 8 steps on the live site
- [ ] Mobile check at about 390 px width: no horizontal scroll, panels readable

## Content honesty

- [ ] Displayed numbers come from live API responses; none are hard-coded
- [ ] Disclaimer visible: Overview, rail, Methodology, Impact
- [ ] "Unknown (no FEMA data)" hatching visible and explained in the legend
- [ ] Equity vs equal described as redistribution, not an increase, when totals are equal
- [ ] Hub details show the authorization warning for schools and private property
- [ ] Devpost text claims no users, partners or real-world impact

## Submission

- [ ] Demo video ≤ 3 min recorded from `docs/DEMO_SCRIPT.md`
- [ ] Devpost fields filled from `docs/DEVPOST_SUBMISSION.md`; live app and video links added
- [ ] Screenshots attached from `docs/img/` (real application captures)
- [ ] Repository link set to https://github.com/renish5609-beep/Crisees
