# SafeWindow

SafeWindow is a research prototype for estimating when villages lose all road access to a flood shelter. The project combines flood observations, road connectivity, shelter locations, rainfall, and a user-adjustable household supply assumption into a date-based isolation timeline.

> **Important:** SafeWindow is not an official warning system, evacuation planner, or emergency decision tool. Its outputs are provisional and must be checked against official alerts and local information.

## Project guide

See [docs/PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md) for the scientific scope, data status, live-data prerequisites, validation commands, and NASA Space Challenge submission assessment.

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

**Updated 24 October 2026.**
- **Rule change.** On 4 of the 19 dates, Otsu finds no dark-water threshold, typically because wind-roughened haor water is not dark. Those maps are now set to unknown instead of being classified with a fixed −18 dB, which caught almost no water. The other 15 maps are unchanged.
- **What changed.** Some isolation and safe-exit dates moved, and the "reconnected" dates disappeared. The five isolated villages, their population, the benchmark scores and both news checks did not change.
- **Where to look.** The previous version is kept in `data/archive/live_v1_2026-10-12/`. Details are in [docs/phase3a_report.md](docs/phase3a_report.md), section 5.

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
| Connected on every date its roads were observed, unknown on the others | 9 |
| Boat-dependent | 2 |

- **Robust to the threshold:** the same five villages are isolated at the 10%, 20% and 40% thresholds.
- **Dates:**
  - Paschim Birgaon is isolated on or before 16 May.
  - Dholkotob and Patharia are isolated between 17 and 23 May; their last safe exit is 16 May.
  - Boromuha and Purba Birgaon are isolated on or before 23 May; no safe exit was observed.
- **Bridges:** water under the 534 mapped road bridges is not counted as flooded road.
- **Not field-checked:** the village dates have not been checked against reports of specific villages.

## Results: May–July 2024 flood, Sunamganj (unseen test)

The same area and the same method were run on the 2024 flood, with no threshold changed (`regions/sunamganj_2024.yaml`, `data/sunamganj_2024/`). Details: [docs/phase3a_report.md](docs/phase3a_report.md).

- **The same five villages are isolated again** at every threshold, and all 16 villages have the same outcome as in 2022.
- **Flood extent vs independent sensors** (UNOSAT FL20240502BGD, 26 June; our maps are 3–7 days away):
  - Pleiades optical, IoU 0.69;
  - SAOCOM L-band radar, IoU 0.74;
  - UNOSAT's Sentinel-1 total water, IoU 0.91.

  Precision is 0.85–0.97 against the independent sensors.
- **Roads:** 56–71% of the road SafeWindow cuts lies on roads UNOSAT marks as flood-affected on the SAOCOM image.
- **News:** the Chhatak–Dowarabazar route, reported inundated on 18 June 2024, is cut on the next radar view (19 June) at every threshold.

## Three floods, one method

The same code and thresholds were used for all three floods; nothing was tuned per flood. Details: `docs/phase3a_report.md` and `docs/phase3b_report.md`.

| | Sunamganj 2022 | Sunamganj 2024 (unseen year) | Trimmu, Pakistan 2025 (unseen country) |
|---|---|---|---|
| Sentinel-1 dates (unusable) | 19 (4) | 24 (5) | 9 (0) |
| Best independent sensor, same day or nearest | Chaohu-1 / RCM-1, same day: IoU 0.81–0.84 | SAOCOM (−7 d) 0.74; Pleiades (+3 d) 0.69 | ICEYE (+1 d) 0.53 |
| Same Sentinel-1 data, other method | UNOSAT: 0.89 | UNOSAT total water: 0.91 | Copernicus EMS: 0.68 (1 Sep), 0.62 (2 Sep) |
| Precision against independent sensors | 0.93–0.95 | 0.85–0.97 | 0.48–0.73 |
| Villages isolated at 20% (stable 10–40%?) | 5 of 16 (yes) | the same 5 of 16 (yes) | 2 of 26 (no: 7 at 10%) |
| Dated road reports | 2 of 2 match | 1 cut on the next view | 1 not seen: man-made breaches, also absent from EMS maps |
| OSM inputs | 4,988 km road, 50 shelters | same | 805 km road, 3 shelters |

The method transfers, with clear limits. Agreement drops where the flood changes within a day or two, where irrigated rice may look like flood, and where OpenStreetMap is thin.

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

## Experimental, not part of SafeWindow results

The `ml/` folder and `app/floodnet_app.py` are side experiments. No SafeWindow flood map, road cut, isolation date or benchmark score uses them.

- **FloodNet classifier** (`ml/floodnet_classifier.py`, `ml/floodnet_model.pt`): labels a whole aerial photo as flooded or not. It is trained on the public FloodNet dataset.
- **Temporal U-Net** (`ml/model.py`, `ml/model.pt`): trained only on the synthetic demo data, so it must not be used for real predictions.

SafeWindow's flood maps come from the rule-based Sentinel-1 method in `pipeline/02a_sentinel1_gee.py`.

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

See [docs/SUBMISSION_STATUS.md](docs/SUBMISSION_STATUS.md) for the evidence gate.
