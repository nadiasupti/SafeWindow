# SafeWindow Live Evidence Status

Updated: 2026-10-12

## Status

**Real-region data build complete. Flood-extent benchmark and news-report road checks complete. Independent review not yet done.**

## What changed on 11 October 2026

The earlier Sentinel-1 rasters were corrupt: every 800 × 800 pixel tile held the whole study area. `safewindow.gee.download_to_grid` set no export region, and it flipped the tile transform. Both are fixed, and `tests/test_gee.py` now covers the tile geometry. Every flood map, road cut, village status and app file was regenerated. Anything built before this date is invalid.

## What changed on 12 October 2026

- **Bridges.** Road cutting ignores water under the 534 mapped OSM road bridges (`processed/bridges.gpkg`, `pipeline/03c_bridges.py`). No village outcome changed. The false cut of the Sunamganj–Sylhet Highway on 6 June is gone.
- **New outcome label.** Villages connected on every date their roads were observed are now `connected_when_seen`, instead of a blanket `uncertain`.
- **Shelters.** The two pharmacies are dropped from the shelter candidates. Unnamed sites are labelled by type.
- **Benchmark.** Extended to four UNOSAT references in three independence tiers.
- **News checks.** Added road checks against two dated news reports (`results/road_reports_verdict.csv`).

## What changed on 24 October 2026

- **Reproduced.** The 19 Sentinel-1 maps were rebuilt from Earth Engine with project `safewindow-2026`. They are pixel-identical to the published maps, and every result file matched (`data/rerun/`, kept locally).
- **Rule change.** On dates where Otsu finds no plausible threshold, the map is now set to unknown instead of being classified at a fixed −18 dB. Those maps had shown almost no water.
  - Affected dates: 18 May, 11 June, 23 June and 5 July. The other 15 maps are unchanged.
  - Rebuilt from the new maps: road status, village status, timeline, news checks and the app package.
  - Unchanged: the 5 isolated villages and their population, the benchmark scores (`build_benchmark.py --check` passes) and both news checks.
  - Changed: some isolation and safe-exit dates, and the "reconnected" dates are gone.
  - The previous version is kept in `data/archive/live_v1_2026-10-12/`.
- **New evidence.** The 2024 flood was run as an unseen test (`data/sunamganj_2024/`). The same 5 villages are isolated.

## Verified outputs

- `processed/study_area.gpkg`: Sunamganj Sadar, Chhatak and Dowarabazar, 1,265 km².
- `processed/grid.json`: 2,473 × 2,081 pixels at 20 m.
- `processed/roads.graphml`: 21,542 junctions and 24,947 road segments.
- `processed/villages.gpkg`: 16 OSM villages, hamlets or towns. Each has a WorldPop 2020 catchment population.
- `processed/shelters_candidates.csv`: 50 OSM shelter candidates, of which 48 are used (pharmacies excluded). These are **not** verified shelters.
- `processed/bridges.gpkg`: 534 OSM road bridges, 18.7 km.
- `processed/rainfall_daily.csv`: NASA GPM IMERG V07, 42 days from 20 May to 30 June 2022.
- `processed/flood/sentinel1_*.tif`: 19 Sentinel-1 flood maps, 16 May to 12 July 2022.
- `processed/modis_flood_area.csv`: MODIS MOD09GA proxy, 87–100% cloud-masked on every date. It is not used for road cutting.
- `results/`: road status, village status, village summary, exit routes, sensitivity, road checks against news reports.
- `app/`: the app package, which passes `validate_app_dataset`.

## Evidence files

| File | Status |
|---|---|
| `benchmark.csv` | Present |
| `benchmark_manifest.json` | Present |
| `model_evaluation.csv` | Present |
| `model_evaluation.json` | Present |
| `source_manifest.json` | Present |
| `science_methods.md` | Present |
| `submission_evidence.json` | Present; status `evidence_ready_review_pending` |

## Remaining steps

1. Independent scientific review by someone outside the team, recorded in `submission_evidence.json`.
2. Check shelters in `shelter_checklist.csv` (a map link is given for each), then run `python scripts/shelter_checklist.py apply` and rerun steps 06, 07 and 08.
3. Collect news or field reports into `validation/news_reports.csv` and run `pipeline/09_validate.py`.
