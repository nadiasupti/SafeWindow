# SafeWindow

**When does a village lose its last road to a flood shelter, and by when must aid arrive?**

SafeWindow turns satellite flood maps into a date-based isolation timeline for every village. It combines Sentinel-1 radar flood maps, OpenStreetMap roads and shelters, NASA rainfall and elevation data, and a household supply assumption. For each village, it answers three questions:

1. **When** is the village cut off from every shelter?
2. **What is the last safe day** to leave, and by which road?
3. **By when must aid arrive**, given how many days of food a household has?

The method was built on the 2022 Sunamganj flood in Bangladesh. With no thresholds changed, it was then tested on the 2024 Sunamganj flood and on the 2025 Chenab–Jhelum flood at Trimmu, Pakistan.

> **Important:** SafeWindow is a research prototype. It is not an official warning system, evacuation planner or emergency decision tool. Always follow official alerts (for example BMD, FFWC and DDM in Bangladesh, or NDMA and PDMA Punjab in Pakistan).

NASA Space Apps Challenge 2026 · Team DeltaSentinels · MIT licence

---

## Contents

- [Results at a glance](#results-at-a-glance)
- [How it works](#how-it-works)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Command reference](#command-reference)
- [Running SafeWindow on a new flood](#running-safewindow-on-a-new-flood)
- [Reproducing the published results](#reproducing-the-published-results)
- [Detailed results](#detailed-results)
- [Repository layout](#repository-layout)
- [Data sources](#data-sources)
- [Limitations](#limitations)
- [Project status](#project-status)
- [Experimental components](#experimental-components)
- [Team and licence](#team-and-licence)

---

## Results at a glance

The same code and the same thresholds were used for all three floods. Nothing was tuned on any reference map.

| | Sunamganj 2022 | Sunamganj 2024 (unseen year) | Trimmu, Pakistan 2025 (unseen country) |
|---|---|---|---|
| Sentinel-1 dates (unclassifiable) | 19 (4) | 24 (5) | 9 (0) |
| Agreement with an independent satellite (IoU) | 0.81–0.84, same day (Chaohu-1, RCM-1) | 0.74 SAOCOM (−7 d); 0.69 Pleiades (+3 d) | 0.53 ICEYE (+1 d) |
| Same Sentinel-1 data, another agency's method (IoU) | 0.89 (UNOSAT) | 0.91 (UNOSAT, total water) | 0.68 (Copernicus EMS) |
| Precision against independent sensors | 0.93–0.95 | 0.85–0.97 | 0.48–0.73 |
| Villages isolated at the 20% cut threshold | 5 of 16 | **the same 5 of 16** | 2 of 26 (7 at the 10% threshold) |
| Dated news reports of cut roads | 2 of 2 match | 1 of 1 matches | 1 not visible (narrow man-made breaches) |

- **The same five villages** (catchment population about 187,800) are isolated in both Sunamganj floods, at every threshold tested.
- **NASA-ISRO NISAR** (L-band radar) sees 94.7–95.8% of SafeWindow's flood as water, in both countries, from an independent satellite and radar band.
- **Weaker at Trimmu.** Agreement is lower there, where the flood doubled within two days, irrigated rice may look like flood, and OpenStreetMap is thin.

---

## How it works

```text
Sentinel-1 radar ──► flood map per date (20 m)       NASA GPM IMERG ──► rainfall
                         │                            NASA NASADEM  ──► slope mask
OpenStreetMap ───► roads, bridges, villages, shelters
                         │
                         ▼
        road segment cut if > 20% of its check-points are flooded
                         │
                         ▼
        village isolated if no road route reaches any shelter
                         │
                         ▼
        isolation date range, last safe exit, aid deadline ──► Streamlit app
```

1. **Flood maps.** Sentinel-1 VV backscatter in Google Earth Engine, with these rules:
   - **Otsu threshold**, kept only within −26 to −12 dB.
   - **3 dB change rule** against a dry-season reference.
   - **NASADEM slope mask** of 5°.

   A date where Otsu finds no plausible threshold is set to *unknown* rather than guessed.
2. **Road cuts.** Every OpenStreetMap road segment gets a check-point every 20 m. Water under mapped bridges is ignored. The cut threshold is 20%, with 10% and 40% as sensitivity tests.
3. **Isolation.** The road network is solved twice per date:
   - once with only the roads seen open;
   - once with every road not seen cut.

   This gives *connected*, *isolated* or *uncertain*, so missing radar data widens the answer instead of hiding it.
4. **Timeline.** Isolation dates are ranges between radar passes. The aid deadline is the earliest possible isolation date plus the household supply days (default 7, adjustable from 2 to 14 in the app).

Full method, assumptions and benchmark design: [data/live/science_methods.md](data/live/science_methods.md).

---

## Installation

You need Python 3.10 or newer. On Windows (PowerShell):

```powershell
git clone https://github.com/nadiasupti/SafeWindow.git
cd SafeWindow
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-pipeline.txt
python -m pip install -e .
```

- **Activation blocked?** If PowerShell blocks `Activate.ps1`, run `Set-ExecutionPolicy -Scope Process Bypass` first, or call `.venv\Scripts\python.exe` directly.
- **macOS or Linux:** activate the environment with `source .venv/bin/activate` instead.

| Requirements file | Use it for |
|---|---|
| `requirements.txt` | The Streamlit app only (this is what Streamlit Community Cloud installs) |
| `requirements-pipeline.txt` | The app plus the full data pipeline, benchmarks and NASA comparisons |
| `requirements-ml.txt` | The experimental machine-learning components (PyTorch) |

**Accounts.** You need these only to rebuild data; the app runs without them.

| Account | Needed for | Setup |
|---|---|---|
| [Google Earth Engine](https://earthengine.google.com) (free, non-commercial) | Sentinel-1, NASADEM, GPM IMERG, WorldPop | `earthengine authenticate`, then `$env:EE_PROJECT="your-project-id"` |
| [NASA Earthdata](https://urs.earthdata.nasa.gov) (free) | OPERA DSWx-S1, NISAR, MCDWD | Log in once with `python -c "import earthaccess; earthaccess.login(persist=True)"` |

---

## Quick start

**Open the app with the real results.** No accounts are needed.

```powershell
python -m streamlit run app/streamlit_app.py
```

The app opens at http://localhost:8501.
- **Choose a flood** in the sidebar: Sunamganj 2022, Sunamganj 2024 or Trimmu 2025.
- **Replay the flood** with the date slider.
- **Click a village** to see its isolation range, safe exit route and aid deadline.

The interface is in English and Bangla.

**Run the synthetic demo.** On Windows, double-click `run_demo.bat`. It sets up the environment, builds an invented demo package in `data_demo/`, validates it and opens the app. The demo data is clearly labelled as synthetic.

---

## Command reference

All commands run from the repository root with the virtual environment active. Environment variables use PowerShell syntax.

### Environment variables

| Variable | Meaning | Default |
|---|---|---|
| `SAFEWINDOW_REGION` | Region file in `regions/` (name without `.yaml`, or a path) | `sunamganj_2022` |
| `SAFEWINDOW_DATA_DIR` | Folder that a pipeline run reads and writes | `data/live` |
| `EE_PROJECT` | Google Earth Engine Cloud project ID | none |

Example: `$env:SAFEWINDOW_REGION="sunamganj_2024"; $env:SAFEWINDOW_DATA_DIR="data/sunamganj_2024"`. Clear both with `Remove-Item Env:SAFEWINDOW_REGION, Env:SAFEWINDOW_DATA_DIR`.

### App

| Task | Command |
|---|---|
| Open the SafeWindow app | `python -m streamlit run app/streamlit_app.py` |
| Build, validate and open the synthetic demo | `python scripts/build_demo.py --keep data_demo --launch` |
| Validate an app data package | `python scripts/inspect_data.py data/live` |

### Pipeline

Run the steps in order for one region and one data folder. Steps marked † need Earth Engine, and ‡ needs Earthdata.

| Step | What it does | Command |
|---|---|---|
| 01 | Study area and the 20 m grid. Admin units come from the region file, or from `area.boundary_file` | `python pipeline/01_study_area.py` |
| 02a † | Sentinel-1 flood map for every date; `--list` shows dates first, `--dates` maps only some | `python pipeline/02a_sentinel1_gee.py` |
| 02b | *Optional.* Register a UNOSAT flood map as an extra source | `python pipeline/02b_unosat.py <flood.shp> --date YYYY-MM-DD --aoi <extent.shp>` |
| 02c ‡ | *Optional.* NASA LANCE MCDWD daily flood product; it keeps only the last ~7 days | `python pipeline/02c_modis.py` |
| 02d † | *Optional.* DEM estimate between radar dates (not for embanked rivers) | `python pipeline/02d_dem_gapfill.py --download`, then `python pipeline/02d_dem_gapfill.py` |
| 02e | Merge flood sources per date; the published results use Sentinel-1 only | `python pipeline/02e_merge_flood.py --sources sentinel1` |
| 03 | Roads, villages and shelter candidates from OpenStreetMap | `python pipeline/03_osm_roads_places.py` |
| 03b † | Population per village from WorldPop; `--buildings` builds candidate settlements from Google Open Buildings | `python pipeline/03b_population.py --worldpop-gee` |
| 03c | Road bridges from OpenStreetMap | `python pipeline/03c_bridges.py` |
| 04 † | Daily NASA GPM IMERG rainfall over the region's rain boxes | `python pipeline/04_rainfall_gpm.py` |
| 05 | Cut roads per date, at 10%, 20% and 40% | `python pipeline/05_cut_roads.py` |
| 06 | Village isolation per date | `python pipeline/06_isolation.py` |
| 07 | Isolation timeline, safe exits and aid deadlines | `python pipeline/07_timeline.py` |
| 08 | Build the app data package | `python pipeline/08_build_app_data.py` |
| 09 | Score isolation against news reports; `--template` creates the input file | `python pipeline/09_validate.py` |
| 10 † | All-in-one build for a current flood, into its own folder | `python pipeline/10_build_live_data.py --days 30` |
| 02e–09 | Rerun the engine steps (02e, 05, 06, 07, 09 if reports exist, 08) after the inputs exist | `python scripts/run_engine.py` |

`10_build_live_data.py` takes its dry reference from the 90 days before the start date. Use it for current floods, not to reproduce the published studies. It refuses to overwrite a folder that holds submission evidence.

### Validation and benchmarks

| Task | Command |
|---|---|
| Re-score the 2022 benchmark from the stored reference masks (no download) | `python scripts/build_benchmark.py --check` |
| Benchmark a region against its references (needs the reference files, see below) | `python scripts/benchmark_region.py regions/sunamganj_2024_benchmark.yaml` |
| Check road cuts against dated news reports (`road_reports` in the region file) | `python scripts/road_reports_check.py` |
| Compare road cuts with an independent flood-affected road map | `python scripts/road_reference_check.py <roads.shp> <extent.shp> --dates 2024-06-29 2024-06-19` |
| Find dates whose Otsu threshold failed | `python scripts/otsu_fallback_check.py data/live data/sunamganj_2024` |
| Check the scientific evidence of a release | `python scripts/verify_submission.py data/live` |
| Run the test suite (73 tests) | `python -m pytest -q` |

### NASA data comparisons

| Task | Command |
|---|---|
| NASA-ISRO NISAR water vs SafeWindow ‡ | `python scripts/nisar_compare.py <out dir> --pair <NISAR date>:<NISAR baseline date>:<SafeWindow date>` |
| NASA OPERA DSWx-S1 "new water" maps ‡ | `python scripts/opera_compare.py <out dir> --dates 2025-08-28 2025-09-01 --dry-start 2025-04-01 --dry-end 2025-05-31` |
| Score two map versions on the same pixels (OPERA, or no slope mask) | `python scripts/ablation_compare.py data/punjab_trimmu_2025 <out dir> --label "NASA OPERA DSWx-S1"` |
| Maps without the NASADEM slope mask †, written to a separate folder | `python pipeline/02a_sentinel1_gee.py --no-slope-mask` |
| NASADEM vs Copernicus DEM for the between-dates estimate † | `python scripts/dem_bathtub_check.py <out dir>` |
| Lag between GPM IMERG rain and the flooded area | `python scripts/rain_flood_lag.py <data dir> <rainfall_daily.csv>` |

`--no-slope-mask` refuses to write into a folder that holds submission evidence.

### Early warning (hindcast)

The rule is learned on one flood and tested on another. It needs rainfall from before the first isolations, so fetch it from April first (†):

```powershell
$env:SAFEWINDOW_REGION="sunamganj_2022"; $env:SAFEWINDOW_DATA_DIR="data/experiments/rain_2022"
python pipeline/04_rainfall_gpm.py --start 2022-04-01 --end 2022-07-15
$env:SAFEWINDOW_REGION="sunamganj_2024"; $env:SAFEWINDOW_DATA_DIR="data/experiments/rain_2024"
python pipeline/04_rainfall_gpm.py --start 2024-04-01 --end 2024-07-31
Remove-Item Env:SAFEWINDOW_REGION, Env:SAFEWINDOW_DATA_DIR

python scripts/early_warning_hindcast.py `
    --train data/live data/experiments/rain_2022/processed/rainfall_daily.csv `
    --test data/sunamganj_2024 data/experiments/rain_2024/processed/rainfall_daily.csv `
    --box meghalaya_upstream_mm --window 3 --lag 0
```

With `--vulnerable-only` the rule ignores rain, and the rainfall files already in the repository are enough (`data/live/processed/rainfall_daily.csv`, `data/sunamganj_2024/processed/rainfall_daily.csv`).

The script refuses to write into a folder that holds submission evidence; pass `--out` for another location.

### Shelters and packaging

| Task | Command |
|---|---|
| List shelter candidates for hand-checking | `python scripts/shelter_checklist.py make` |
| Use only the confirmed shelters, then rerun steps 06–08 | `python scripts/shelter_checklist.py apply` |
| Rebuild the data manifest | `python scripts/build_manifest.py data/live` |
| Build a submission package (only from verified evidence) | `python scripts/build_submission_package.py data/live --output <folder>` |

---

## Running SafeWindow on a new flood

A new flood needs a region file, not code changes. The method and its thresholds are the same everywhere.

1. Copy `regions/sunamganj_2022.yaml` to `regions/<place>_<year>.yaml` and edit it. It holds:
   - the area, dates and projection;
   - rainfall boxes;
   - languages and warning agencies;
   - shelters and dated news reports.

   All fields are described in [regions/README.md](regions/README.md).
2. Point the pipeline at it, in its own data folder:

   ```powershell
   $env:EE_PROJECT="your-project-id"
   $env:SAFEWINDOW_REGION="<place>_<year>"
   $env:SAFEWINDOW_DATA_DIR="data/<place>_<year>"
   ```

3. Run pipeline steps 01 to 08 in order (see [Pipeline](#pipeline)).
4. Open the app. Every folder `data/*/app` with a built package appears in the flood selector.

Where OpenStreetMap has few shelters, give a local list with `shelters_csv` in the region file. It needs the columns `name, lat, lon`, and optionally `type, capacity, verified_by`.

---

## Reproducing the published results

| Result | How to reproduce | Needs |
|---|---|---|
| 2022 benchmark scores | `python scripts/build_benchmark.py --check` | Nothing; the reference masks are in `data/live/benchmark/` |
| 2022 road and news checks | `python scripts/road_reports_check.py` | Nothing |
| 2022 flood maps | `$env:SAFEWINDOW_DATA_DIR="data/rerun"`, then run 02a, 02e, 05, 06 and 07, as in [science_methods.md](data/live/science_methods.md), section 10 | Earth Engine |
| 2024 and Trimmu benchmarks | Set the region (see the example under [Environment variables](#environment-variables)), then run `benchmark_region.py` with that region's benchmark file | Reference files downloaded into `data/sources/`, from the URLs listed in each `*_benchmark.yaml` |
| Hindcast | The commands under [Early warning (hindcast)](#early-warning-hindcast) | Earth Engine for the rain rule; nothing for `--vulnerable-only` |
| Rain lag | Fetch rainfall from before the flood with step 04 (`--start`) into a separate folder, then `rain_flood_lag.py` | Earth Engine |
| NISAR and OPERA comparisons | `nisar_compare.py`, `opera_compare.py` | Earthdata login |

**Do not overwrite `data/live`.** It holds the 2022 study results and the submission evidence. Write every rebuild or experiment to a new folder.

**Reproducibility check.** Rebuilt from Earth Engine with the code in this repository, the 19 published 2022 flood maps are pixel-identical, and every result file matches.

Sources and parameters are recorded in [data/live/source_manifest.json](data/live/source_manifest.json).

---

## Detailed results

### May–July 2022, Sunamganj, Bangladesh

The study area is Sunamganj Sadar, Chhatak and Dowarabazar (1,265 km²), with 19 Sentinel-1 dates from 16 May to 12 July 2022.

**Flood extent vs UNOSAT analyses (event FL20220525BGD).** Grouped by independence from SafeWindow's own data:

| Tier | Reference | Area compared | IoU (95% CI) | Precision | Recall |
|---|---|---|---|---|---|
| A: other satellite, same day | Chaohu-1, 25 May 2022 | 25.1 km² | 0.835 (0.786–0.876) | 0.930 | 0.891 |
| A: other satellite, same day | RCM-1, 18 Jun 2022 | 98.4 km² | 0.808 (0.788–0.829) | 0.953 | 0.842 |
| B: other satellite, next day | RCM-1, 19 Jun 2022 | 1,248 km² | 0.889 (0.884–0.895) | 0.928 | 0.956 |
| C: same Sentinel-1 data, UNOSAT method | Sentinel-1, 25 May 2022 | 1,262 km² | 0.895 (0.889–0.900) | 0.978 | 0.913 |

Confidence intervals come from a 1 km block bootstrap. UNOSAT products are preliminary satellite analyses, not field ground truth.

**Road cuts vs dated news reports:**
- **June.** The Daily Star reported Sunamganj's road link cut from 16 June 2022. The model has the Sunamganj–Sylhet Highway route open on 6 June and cut on 16 June, at the 10%, 20% and 40% thresholds alike.
- **May.** The Chhatak–Dowarabazar road link was reported cut on 19 May. The model has it cut on the next radar view, 23 May, at the 10% and 20% thresholds, but not at 40%.

**Village isolation at the 20% cut threshold:**

| Outcome | Villages |
|---|---|
| Isolated at some point | 5 (catchment population about 187,800, WorldPop 2020) |
| Connected on every date its roads were observed, unknown on the others | 9 |
| Boat-dependent (more than 500 m from a mapped road) | 2 |

| Village | Isolation | Last safe exit | Aid deadline (7 supply days) |
|---|---|---|---|
| Paschim Birgaon | on or before 16 May | none observed | 23 May |
| Dholkotob | between 17 and 23 May | 16 May | 24 May |
| Patharia | between 17 and 23 May | 16 May | 24 May |
| Boromuha | on or before 23 May | none observed | 30 May |
| Purba Birgaon | on or before 23 May | none observed | 30 May |

The same five villages are isolated at the 10%, 20% and 40% thresholds. The village dates have not been checked against reports about specific villages.

**Rule update, 24 October 2026.** On 4 of the 19 dates, Otsu finds no dark-water threshold, typically because wind-roughened haor water is not dark. Those maps are now unknown instead of being classified with a fixed −18 dB, which caught almost no water. This moved some isolation and safe-exit dates. It did not change the five isolated villages, their population, the benchmark scores or the news checks. The check is `scripts/otsu_fallback_check.py`.

### May–July 2024, Sunamganj (unseen year)

The same area, method and thresholds were used, with 24 Sentinel-1 dates (`regions/sunamganj_2024.yaml`, `data/sunamganj_2024/`).

- **The same five villages are isolated** at every threshold, and all 16 villages have the same outcome as in 2022.
- **Flood extent vs independent sensors** (UNOSAT FL20240502BGD, 26 June; our maps are 3–7 days away):

  | Reference | IoU |
  |---|---|
  | Pleiades (optical) | 0.69 |
  | SAOCOM (L-band radar) | 0.74 |
  | UNOSAT Sentinel-1 total water | 0.91 |

  Precision is 0.85–0.97 against the independent sensors.
- **Roads.** 56–71% of the road SafeWindow cuts lies on roads that UNOSAT marks as flood-affected on the SAOCOM image.
- **News.** The Chhatak–Dowarabazar route, reported inundated on 18 June 2024, is cut on the next radar view (19 June) at every threshold.

### August–September 2025, Trimmu, Punjab, Pakistan (unseen country)

The study area is the Copernicus EMS EMSR838 AOI 5 polygon at the Chenab–Jhelum confluence (1,014 km², `regions/punjab_trimmu_2025.yaml`). There are 9 Sentinel-1 dates, all with full coverage. The projection is UTM 43N.

- **Flood extent vs Copernicus EMS:**
  - IoU 0.53 against ICEYE (X-band radar), one day apart;
  - IoU 0.68 against EMS's own analysis of the same Sentinel-1 image.
- **Villages.** At the 20% threshold, 2 villages are isolated (about 75,300 people). The result is the same with town centres as destinations instead of the 3 OpenStreetMap shelter candidates (`regions/punjab_trimmu_2025_hubs.yaml`).
- **News.** The reported Shorkot–Garh Maharaja road breaches were narrow, deliberate cuts to release water. They do not appear in SafeWindow's maps or in the Copernicus EMS maps.

### What NASA data adds (measured)

| NASA data | Test | Result |
|---|---|---|
| **NISAR** (NASA-ISRO, L-band) | SafeWindow's flood vs NISAR water, 1–2 days apart, Sunamganj and Trimmu 2026 | 94.7–95.8% of SafeWindow's flood is also water in NISAR. NISAR also sees water under crops, which SafeWindow intentionally does not count. |
| **OPERA DSWx-S1** | Both maps against the same Copernicus EMS references, Trimmu 2025 | Where SafeWindow and OPERA agree, 84–92% of the flood is confirmed by EMS. This gives a high-confidence class. |
| **GPM IMERG** | Which rain window best tracks the flooded area | Upstream rain leads the flood by about 5 days at Trimmu, and by 0–3 days in the haor. Exploratory: about 9 radar dates per flood. |
| **NASADEM** slope mask | Benchmark with and without the mask, 3 floods | In these flat floodplains the mask lowers IoU by 0.006–0.054. Kept unchanged, to avoid tuning on test data. |
| **NASADEM** vs Copernicus GLO-30 | Redrawing observed floods from DEM height | No clear difference |
| **LANCE MCDWD** | Archive search | Only the last ~7 days are kept, so it is unusable for past floods |

### Early warning (hindcast)

The rule was learned on 2022 and tested on 2024, which had 19 new isolations:

| Rule | Hits | Misses | False alarms |
|---|---|---|---|
| Persistence ("the next date looks like today") | 0 | 19 | 0 |
| Warn the villages isolated in 2022 | 19 | 0 | 32 |
| The same, only when 3-day upstream GPM rain reaches the trigger (318 mm) | 5 | 14 | 0 |

- **Vulnerable villages are the strongest signal.** The list of villages isolated in 2022 flagged every new isolation 2–7 days ahead.
- **The rain trigger is too strict.** It is learned from the rain known on the radar date before each 2022 isolation. It removed every false alarm but missed 14 of 19 isolations, so it is not used in the app.
- **The reverse test is not informative.** Trained on 2024 and tested on 2022, the rule scores 20 of 21. But in 2022 the vulnerable villages were isolated on almost every date.

---

## Repository layout

```text
SafeWindow/
├── app/                    Streamlit app (streamlit_app.py); floodnet_app.py is experimental
├── pipeline/               Numbered data pipeline, steps 01–10
├── safewindow/             Core library: region files, road cutting, isolation, timeline, validation
├── scripts/                Benchmarks, NASA comparisons, hindcast, demo and packaging tools
├── regions/                One YAML file per flood, plus benchmark reference lists
├── locales/                App text per language (en.json, bn.json)
├── tests/                  pytest suite
├── data/
│   ├── live/               Sunamganj 2022: results, benchmark, evidence (app default)
│   ├── sunamganj_2024/     Sunamganj 2024 results
│   ├── punjab_trimmu_2025/ Trimmu, Pakistan 2025 results
│   ├── sunamganj_2026/     2026 monsoon, used for the NISAR check
│   └── punjab_trimmu_2026/ 2026 monsoon, used for the NISAR check
├── ml/                     Experimental machine-learning components
├── run_demo.bat            One-click synthetic demo (Windows)
└── requirements*.txt       Dependencies (app, pipeline, ML)
```

Some folders are created locally and are not in git:
- `data/sources/` holds the downloaded reference maps.
- `data/experiments/` and `data/rerun/` hold experiment and rebuild runs.
- `data_demo/` holds the generated synthetic demo.

---

## Data sources

All inputs are free and public.

| Data | Provider | Used for |
|---|---|---|
| Sentinel-1 GRD | ESA Copernicus, via Google Earth Engine | Flood maps |
| NASADEM | NASA | Slope mask |
| GPM IMERG V07 | NASA | Daily rainfall, lag analysis, hindcast |
| OPERA DSWx-S1 | NASA JPL, via NASA Earthdata | Confidence comparison |
| NISAR GCOV | NASA-ISRO, via NASA Earthdata | Independent L-band check |
| LANCE MCDWD, MODIS MOD09GA | NASA | Tested; not usable for these floods (archive length, cloud) |
| Copernicus GLO-30 DEM | ESA | Between-dates estimate |
| OpenStreetMap | OpenStreetMap contributors (ODbL) | Roads, bridges, villages, shelter candidates |
| WorldPop 2020 | WorldPop | Village catchment population |
| UNOSAT FL20220525BGD, FL20240502BGD | UNITAR-UNOSAT | Benchmarks (Bangladesh) |
| Copernicus EMS EMSR838 | European Commission | Benchmark (Pakistan) |
| News reports | The Daily Star, The Daily Observer, Dawn | Road-cut checks |

The OpenStreetMap data is a snapshot from October 2026, used for all three floods.

---

## Limitations

- **Gaps in observation.** Radar passes are days apart, so isolation dates are ranges, not exact days. Some dates cover only part of the area.
- **OpenStreetMap is incomplete.**
  - The shelters are unverified candidates (schools, clinics and offices).
  - Trimmu has only 3 shelter candidates.
  - Roads built after a flood are included.
- **Household supply days** are an assumption, not a measured value.
- **References are not ground truth.** UNOSAT and Copernicus EMS products are preliminary satellite analyses, and news reports are sanity checks.
- **Weaker in some places.** Agreement is lower where the flood changes within a day or two, or where irrigated rice may look like flood.
- **No validated forecast.** The rain trigger did not beat the vulnerable-village list.
- **Not for emergency use.** Results must not be used to make emergency decisions without official sources.

---

## Project status

**Complete:**
- real-region results for three floods in two countries;
- independent flood-extent benchmarks with confidence intervals;
- road checks against dated news reports;
- an independent NISAR radar check;
- a reproducibility check;
- a source manifest and a methods document.

**Open:**
- an independent scientific review;
- hand-verified shelter lists;
- a check of village isolation dates against field or news reports.

Until a review is recorded, `scripts/verify_submission.py data/live` reports the release as unverified, by design.

---

## Experimental components

The `ml/` folder and `app/floodnet_app.py` are side experiments. No SafeWindow flood map, road cut, isolation date or benchmark score uses them. See [ml/README.md](ml/README.md).

- **FloodNet classifier** (`ml/floodnet_model.pt`). It labels a whole aerial photo as flooded or not, and is trained on the public FloodNet dataset.
- **Temporal U-Net** (`ml/model.pt`). It is trained only on the synthetic demo data and must not be used for real predictions.

---

## Team and licence

**Team DeltaSentinels**, NASA Space Apps Challenge 2026: Farhan Labib and Nadia Supti.

The code is released under the MIT licence (see [LICENSE](LICENSE)). Data products keep the licences of their providers.
