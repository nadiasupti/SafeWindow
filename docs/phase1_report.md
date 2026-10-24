# Phase 1 report: reproducing the 2022 results

Date: 24 October 2026. Earth Engine project: `safewindow-2026` (non-commercial, Community tier).
Rerun outputs are in `data/rerun/` (kept locally, not in git). `data/live/` was not changed.

## Summary

| Check | Result |
|---|---|
| 19 Sentinel-1 flood maps regenerated from Earth Engine | **100% pixel-identical** to `data/live`; every Otsu threshold identical |
| Road cuts, village status, timeline, sensitivity, exit routes (same OSM snapshot) | **All 10 result CSVs and `exit_routes.gpkg` identical** (473,993 road-date rows, 912 village-date rows) |
| News-report road checks (`scripts/road_reports_check.py`) | **Identical** (`road_reports_check.csv`, `road_reports_verdict.csv`) |
| Benchmark audit (Phase 1.3) | **No problems**: see [phase1_benchmark_audit.md](phase1_benchmark_audit.md) |
| Main app without torch (Phase 1.5) | Runs; first load 2.9–3.8 s, no exceptions |
| Test suite | 47 passed (32 original + 15 region tests from Phase 2) |

The published 2022 results can be rebuilt from public data with the code in this repository.

## How the rerun was done

The published maps used the dry reference February–March 2022. `pipeline/10_build_live_data.py` instead uses the 90 days before the start date, so it would **not** reproduce them. The steps were run one by one instead, as in `data/live/science_methods.md` section 10:

```powershell
$env:EE_PROJECT="safewindow-2026"
$env:SAFEWINDOW_DATA_DIR="data/rerun"
# study_area.gpkg and grid.json copied from data/live/processed so the grid is identical
.venv\Scripts\python.exe pipeline\02a_sentinel1_gee.py
# OSM snapshot files copied from data/live/processed (roads, villages, shelters, bridges)
.venv\Scripts\python.exe pipeline\02e_merge_flood.py --sources sentinel1
.venv\Scripts\python.exe pipeline\05_cut_roads.py
.venv\Scripts\python.exe pipeline\06_isolation.py
.venv\Scripts\python.exe pipeline\07_timeline.py
.venv\Scripts\python.exe scripts\road_reports_check.py
```

The comparison script recorded each map's identical-pixel share, its unknown and flooded shares, and IoU. All 19 dates scored 100% / 1.0.

## Findings

1. **The OSM snapshot is from October 2026, not 2022.** `source_manifest.json` dates it to 9 October 2026. A fresh download today returns the same 21,542 junctions, 24,947 segments and 16 villages. So the 2022 flood is analysed on 2026 roads, and roads built after 2022 are included. **Possible fix:** query OSM as it was in May 2022 through Overpass's `[date:"2022-05-15T00:00:00Z"]` setting, and report how much the result changes.
2. **The shelter download no longer works on overpass-api.de.** The query repeats the area outline once for each of its 10 tags, and the server now rejects it as too large (HTTP 413). **Fix applied** in `pipeline/03_osm_roads_places.py`: the shelter query polygon is simplified by about 50 m, which is well inside the 1 km buffer. Tests still pass. The public server also returned 502 under load, and its notice says automated, high-volume use should run a local Overpass instance.
3. **`10_build_live_data.py` is for current floods only.** It is not a reproduction tool, because its dry reference differs from the published method.
4. **`ml/` and `app/floodnet_app.py` stay in place** (moving them would break imports). README now has an "Experimental, not part of SafeWindow results" section.
5. **torch removed from `requirements.txt`** after checks. The main app imports no torch, a clean venv with only `requirements.txt` runs the app, and the full suite passes with `requirements-ml.txt`. The FloodNet app needs `requirements-ml.txt`.

## Fresh-OSM check

On 24 October 2026, today's OpenStreetMap data was downloaded again into `data/experiments/rerun_osm2026/`:

| Layer | Snapshot (9 Oct 2026) | Today (24 Oct 2026) |
|---|---|---|
| Road network | 21,542 junctions, 24,947 segments, 4,988 km | identical |
| Villages | 16 | identical |
| Shelter candidates | 50 | 50, same 50 OSM ids |
| Road bridges | 534, 18.7 km | 534, 18.7 km, same 534 OSM ids |

Every input to the engine is the same, so a fresh-OSM run gives the same results. Today's shelters and bridges were fetched separately, without downloading the roads again: overpass-api.de and two mirrors (kumi.systems, private.coffee) kept timing out or returning 502 on the full road query. The retry script waits 1, 3 and 7 minutes between tries.

The issue in Finding 1 still applies: the 2022 flood is analysed on 2026 roads.
