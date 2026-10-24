# Phase 2 report: a system for any region

Date: 24 October 2026. Test suite: **57 passed** (32 original + 25 new).

## What changed

| Step | Done | Where |
|---|---|---|
| 2.1 Region files | `regions/sunamganj_2022.yaml`; how-to in `regions/README.md` | `regions/` |
| 2.2 config from the region | `SAFEWINDOW_REGION` picks the file. Method thresholds stay in `config.py`, the same for every region | `safewindow/region.py`, `safewindow/config.py` |
| 2.3 Projection | `crs: auto` takes the UTM zone of the bbox centre and warns if the area spans two zones or is wider than 6°; an explicit `EPSG:` code overrides it | `safewindow/region.py` |
| 2.4 Candidate settlements | `settlements: open_buildings` clusters Google Open Buildings. They are labelled **"Candidate settlement"**, and `processed/settlements_check.json` measures agreement with OSM villages | `pipeline/03b_population.py` |
| 2.5 Local shelter list | `shelters_csv` in the region file replaces the OSM candidates | `safewindow/places.py` |
| 2.6 Languages | App text moved to `locales/en.json` and `locales/bn.json`. Languages, warning agencies and rainfall labels come from the region | `locales/`, `app/streamlit_app.py` |
| 2.7 Regression | Same results as before (below) | `tests/test_region.py`, `tests/test_app.py`, `tests/test_places.py` |

Other fixes found on the way:

- **WorldPop was hard-coded to Bangladesh (`"BGD"`).** Any other country would have had zero population, with no error. It now comes from `area.iso3`, and the step stops if WorldPop has no image for that code.
- The OSM search words "Upazila" and "District" now come from the region (`admin_unit`, `parent_unit`), e.g. "Tehsil" in Pakistan.
- `meta.json` records the region, and the app shows an error if the data and `SAFEWINDOW_REGION` do not match.
- New dependency: `PyYAML` (in `requirements.txt`, `pyproject.toml`, `environment.yml`).

## Regression evidence

1. **Engine:** with the region-based config, steps 02e, 05, 06 and 07 on the regenerated maps give **all 10 result CSVs identical** to `data/live/results`.
2. **App:** every visible text was dumped before and after the locale refactor: titles, captions, markdown, metrics, tables, SMS preview and messages. That covered 10 page states (English and Bangla × no village, an isolated village, a village isolated on the first image, a connected-when-seen village, a boat-dependent village). **No difference.** Chart labels are covered by unit tests.
3. **Deployment venv** (no torch): the app runs, and first load takes 3.8 s.

## Candidate settlements in Sunamganj (2.4 trial)

Run in `data/experiments/settlements_2022/` (it does not affect `data/live`):

| | Value |
|---|---|
| Open Buildings (confidence ≥ 0.75) in the study area | 71,711 |
| Candidate settlements (DBSCAN, 60 m, ≥ 10 buildings) | **881** (vs 16 OSM villages) |
| Buildings not in any cluster | 43,683 (61%) |
| OSM villages with a cluster within 1 km | 7 of 16 (44%) |
| Clusters with an OSM village within 1 km | 29 of 881 (3%) |
| Population of all catchments (WorldPop 2020) | 1,011,278 |

**Reading this:** clusters give far more places than OSM, but the agreement is weak. 61% of buildings are left unclustered, probably because haor homesteads are spread out on raised mounds rather than in dense blocks. The 60 m / 10-building setting comes from denser terrain. **Do not switch the main results to candidate settlements yet.** Next:

- try a few cluster settings and compare them with OSM villages and upazila boundaries;
- then report the chosen setting and its match rate.

Neither source is ground truth.

## How to add a new flood

See `regions/README.md`. In short: copy the region file, edit it, set `SAFEWINDOW_REGION` and `SAFEWINDOW_DATA_DIR`, then run the pipeline.
