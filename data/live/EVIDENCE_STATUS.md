# SafeWindow Live Evidence Status

Updated: 2026-10-11

## Status

**Real-region data build complete. Flood-extent benchmark complete. Independent review not yet done.**

## What changed on 11 October 2026

The earlier Sentinel-1 rasters were corrupt: every 800 × 800 pixel tile held the whole study area. `safewindow.gee.download_to_grid` set no export region, and it flipped the tile transform. Both are fixed, and `tests/test_gee.py` now covers the tile geometry. Every flood map, road cut, village status and app file was regenerated. Anything built before this date is invalid.

## Verified outputs

- `processed/study_area.gpkg`: Sunamganj Sadar, Chhatak and Dowarabazar, 1,265 km².
- `processed/grid.json`: 2,473 × 2,081 pixels at 20 m.
- `processed/roads.graphml`: 21,542 junctions and 24,947 road segments.
- `processed/villages.gpkg`: 16 OSM villages, hamlets or towns. Each has a WorldPop 2020 catchment population.
- `processed/shelters_candidates.csv`: 50 OSM shelter candidates. These are **not** verified shelters.
- `processed/rainfall_daily.csv`: NASA GPM IMERG V07, 42 days from 20 May to 30 June 2022.
- `processed/flood/sentinel1_*.tif`: 19 Sentinel-1 flood maps, 16 May to 12 July 2022.
- `processed/modis_flood_area.csv`: MODIS MOD09GA proxy, 87–100% cloud-masked on every date. It is not used for road cutting.
- `results/`: road status, village status, village summary, exit routes, sensitivity.
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

1. Independent scientific review, recorded in `submission_evidence.json`.
2. Hand-verify 15–30 shelters into `processed/shelters_verified.csv`.
3. Collect news or field reports into `validation/news_reports.csv` and run `pipeline/09_validate.py`.
