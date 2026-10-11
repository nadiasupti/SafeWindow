# SafeWindow Project Guide

## Mission

SafeWindow is a research prototype for estimating when villages in Sunamganj, Bangladesh, lose all road access to a flood shelter. It combines flood observations, road accessibility, shelter locations, rainfall, and a household-supply assumption into a date-based isolation timeline.

The project does **not** provide an official warning, evacuation order, or emergency decision.

## What is complete

- Deterministic synthetic demo data for local development.
- Flood raster merge and road-cut analysis.
- Village isolation and shelter-route analysis.
- Survival Clock and date-aware route calculations.
- English and Bengali Streamlit interface.
- Current public-data pipeline for MODIS, Sentinel-1, GPM IMERG, NASADEM, WorldPop, and OSM.
- Real-region results for the May–July 2022 flood: 19 Sentinel-1 flood maps, road cuts, village isolation and aid deadlines.
- Flood-extent benchmark against four UNOSAT analyses in three independence tiers, with bootstrap confidence intervals (`scripts/build_benchmark.py`).
- Road-cut checks against dated news reports (`scripts/road_reports_check.py`).
- Bridge-aware road cutting, so water under a mapped bridge does not cut the road (`pipeline/03c_bridges.py`).
- Source manifest and methods document in `data/live/`.
- Source provenance, hashes, and output validation.
- Regression tests for engine behavior, route availability, classifier prediction, and app artifacts.

## Data status

- **Synthetic demo:** invented terrain, roads, flood, villages, and shelters. Clearly labelled as synthetic.
- **Live data (`data/live`):** real results for the 2022 flood, regenerated on 11 October 2026 after the Earth Engine tile-export fix. Rebuilding needs Earth Engine authentication and `EE_PROJECT`.
- **No source should be treated as ground truth:** flood maps have cloud/radar gaps, OSM is incomplete, and the supply-day value is an assumption.

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-pipeline.txt
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe scripts\build_demo.py --keep data_demo
.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py
```

On Windows, run `run_demo.bat`.

## Live data

```powershell
earthengine authenticate
$env:EE_PROJECT="your-project-id"
$env:SAFEWINDOW_DATA_DIR="data/current"
.venv\Scripts\python.exe pipeline\10_build_live_data.py
.venv\Scripts\python.exe scripts\inspect_data.py data/current
```

The live pipeline writes to the folder in `SAFEWINDOW_DATA_DIR`. The default, `data/live`, holds the 2022 study results and evidence, and the script refuses to rebuild it unless `--overwrite-evidence` is given. It needs Earth Engine credentials. Earthdata login is needed only for the optional MCDWD route in `02c_modis.py`.

## Validation

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts\inspect_data.py data_demo
```

## Scientific limitations

- Flood status is inferred from incomplete observations and is not a direct ground truth.
- Dates between observations are ranges, not exact flood events.
- Shelter and road coverage depends on OSM and manual verification.
- The Supply Day value is user-adjustable and must not be interpreted as a measured household value.
- Evaluation results are nuanced by source, date, and location.
- The application is a research prototype, not an official emergency system.

## NASA Space Challenge submission status

The repository has real-region results, a four-reference flood-extent benchmark with confidence intervals, road checks against dated news reports, a source manifest and a methods document. Still missing: an independent scientific review, hand-verified shelters, and a check of village isolation dates against field or news reports.

A verified submission release must pass:

```powershell
.venv\Scripts\python.exe scripts\verify_submission.py data/live
.venv\Scripts\python.exe scripts\build_submission_package.py data/live
```

The verifier intentionally fails for demo-only or unverified data. See [SUBMISSION_STATUS.md](SUBMISSION_STATUS.md) for the full evidence requirements.
