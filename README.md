# SafeWindow

SafeWindow is a research prototype for estimating when villages lose all road access to a flood shelter. The project combines flood observations, road connectivity, shelter locations, rainfall, and a user-adjustable household supply assumption into a date-based isolation timeline.

> **Important:** SafeWindow is not an official warning system, evacuation planner, or emergency decision tool. Its outputs are provisional and must be checked against official alerts and local information.

## Project guide

See [PROJECT_GUIDE.md](PROJECT_GUIDE.md) for the scientific scope, data status, live-data prerequisites, validation commands, and NASA Space Challenge submission assessment.

## Quick start

### Windows demo

Run `run_demo.bat`. The launcher creates or updates the isolated Python environment, builds a deterministic synthetic package, validates it, and opens the application.

### Manual commands

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-pipeline.txt
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe scripts\build_demo.py --keep data_demo
.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py
```

## Live data

The live-data pipeline requires Earth Engine authentication. Earthdata login is needed only for the optional MCDWD download in `02c_modis.py`.

```powershell
earthengine authenticate
$env:EE_PROJECT="your-project-id"
$env:SAFEWINDOW_DATA_DIR="data/current"
.venv\Scripts\python.exe pipeline\10_build_live_data.py
.venv\Scripts\python.exe scripts\inspect_data.py data/current
```

The app defaults to `data/live`, which holds the May–July 2022 study results and the submission evidence. The live build refuses to overwrite it, so build current floods into their own folder as above. The synthetic package remains available in `data_demo` and is explicitly labelled as invented.

## Results: May–July 2022 flood, Sunamganj

All results come from 19 Sentinel-1 flood maps regenerated on 11 October 2026. That rerun followed a fix to the Earth Engine tile export: before it, every tile repeated the whole study area, so earlier outputs were invalid. Full method and limits: [data/live/science_methods.md](data/live/science_methods.md).

**Flood extent vs UNOSAT analyses.** None of these was used to build or tune SafeWindow. They are grouped by independence:

| Tier | Reference | Area compared | IoU (95% CI) | Precision | Recall |
|---|---|---|---|---|---|
| A: other satellite, same day | Chaohu-1, 25 May 2022 | 25.1 km² | 0.835 (0.786–0.876) | 0.930 | 0.891 |
| A: other satellite, same day | RCM-1, 18 Jun 2022 | 98.4 km² | 0.808 (0.788–0.829) | 0.953 | 0.842 |
| B: other satellite, next day | RCM-1, 19 Jun 2022 | 1,248 km² | 0.889 (0.884–0.895) | 0.928 | 0.956 |
| C: same Sentinel-1 data, UNOSAT method | Sentinel-1, 25 May 2022 | 1,262 km² | 0.895 (0.889–0.900) | 0.978 | 0.913 |

These are preliminary satellite analyses, not field ground truth.

**Road cuts vs dated news reports** (`scripts/road_reports_check.py`):
- **June:** The Daily Star reported Sunamganj's road link cut from 16 June 2022. The model has the Sunamganj–Sylhet Highway route open on 6 June and cut on 16 June, at the 10%, 20% and 40% thresholds alike.
- **May:** the Chhatak–Dowarabazar road link was reported cut on 19 May. The model has it cut on the next radar view, 23 May, at the 10% and 20% thresholds, but not at 40%.

**Village isolation at the 20% cut threshold:**

| Outcome | Villages |
|---|---|
| Isolated at some point | 5 (catchment population about 187,800, WorldPop 2020) |
| Connected on every date its roads were observed (9 of 19) | 8 |
| Boat-dependent | 2 |
| Connected on all 19 dates | 1 |

- **Robust to the threshold:** the same five villages are isolated at the 10%, 20% and 40% thresholds.
- **Bridges:** water under the 534 mapped road bridges is not counted as flooded road.
- **Not field-checked:** the village dates have not been checked against reports of specific villages.

**Reproducing the results.** Run `scripts/build_benchmark.py` and `scripts/road_reports_check.py`. Sources and parameters are listed in [data/live/source_manifest.json](data/live/source_manifest.json).

## Tests

```powershell
.venv\Scripts\python.exe -m pytest -q
```

The suite covers the road-cutting and isolation engine (including the bridge rule), timeline outcomes, date-aware routes, Earth Engine tile geometry, benchmark scoring, shelter cleaning, FloodNet dataset/checkpoint behavior, and generated app artifact validation.

## Architecture

```text
Public sources
  -> pipeline/01-10
  -> processed results
  -> pipeline/08_build_app_data.py
  -> data/live/app or data_demo/app
  -> Streamlit application
```

The separate FloodNet classifier is retained for classifier research. It is not the same model as the temporal flood segmentation pipeline.

## Scientific limitations

- Flood observations contain cloud and radar gaps.
- Dates between observations are ranges, not exact flood events.
- OSM roads and shelters are incomplete and must be verified before operational use.
- Household supply days are an assumption, not a measured field value.
- News-report validation is a sanity check, not ground truth.
- Results must not be used to make emergency decisions without official sources.

## Submission readiness

The repository now contains:
- real-region results;
- a flood-extent benchmark against four UNOSAT analyses, with confidence intervals;
- road checks against dated news reports;
- a source manifest and a methods document.

Three things are still open:
- an independent scientific review;
- hand-verified shelters;
- a check of village isolation dates against field or news reports.

`scripts/verify_submission.py data/live` therefore still fails, but only because no independent review is recorded.

See [SUBMISSION_STATUS.md](SUBMISSION_STATUS.md) for the evidence gate.
