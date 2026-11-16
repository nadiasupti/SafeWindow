# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

SafeWindow turns satellite flood maps into a date-based isolation timeline for every village. It answers when a village loses its last road to a flood shelter, when its road was last seen passable, and when household supplies may run out (an estimate). It was built for NASA Space Apps 2026 ("Dancing with the SARs"). It has three parts:

- a Python science pipeline and library;
- a React PWA for villagers, hosted on Firebase;
- Streamlit apps (a research app and an admin panel).

The README is the full reference for commands, results and data sources. This file covers what you need to work on the code.

## Commands

The project is developed on Windows. Commands run from the repository root with the virtual environment active (`.venv\Scripts\Activate.ps1`).

```powershell
# Python setup
python -m pip install -r requirements-pipeline.txt   # requirements.txt = Streamlit app only; requirements-ml.txt = PyTorch experiments
python -m pip install -e .

# Python tests (pytest, testpaths = tests/)
python -m pytest -q
python -m pytest tests/test_watch.py -q              # one file
python -m pytest tests/test_watch.py -k "name" -q    # one test

# Mobile app (pwa/)
python scripts/build_pwa.py      # export data/*/app + analyses into pwa/public/data/ (run after any data change)
cd pwa; npm install; npm run dev # or: npm run build; npm run preview (http://localhost:4173)
npm run lint                     # oxlint
npm test                         # node --test tests/rescue.test.mjs
cd pwa/rules-tests; npm test     # Firestore security rules against the emulator (npm run test:e2e for auth+firestore)
firebase deploy --only hosting   # publish pwa/dist (project in .firebaserc)

# Streamlit apps
python -m streamlit run app/streamlit_app.py   # research app, http://localhost:8501
run_admin.bat                                  # admin panel, http://127.0.0.1:8502 (needs the Firebase Admin key)

# Checks of the published evidence
python scripts/build_benchmark.py --check      # re-score the 2022 benchmark, no download
python scripts/verify_submission.py data/live
```

Rebuilding flood data needs Google Earth Engine (`earthengine authenticate`, `$env:EE_PROJECT=...`). NISAR, OPERA and MCDWD need a NASA Earthdata login via `earthaccess`. The apps and tests need neither.

## Architecture

### One flood = one region file + one data folder

- **Selection.** `safewindow/config.py` reads two environment variables:
  - `SAFEWINDOW_REGION` picks a YAML file in `regions/` (default `sunamganj_2022`).
  - `SAFEWINDOW_DATA_DIR` picks the data folder (default `data/live`).
- **What lives where.**
  - Settings that vary per flood live in the region file: area, CRS, dates, rain boxes, shelters, news reports and languages. The fields are documented in `regions/README.md`.
  - Method constants are the same for every flood and live in `config.py`: 20 m grid, 20% cut threshold with 10%/40% sensitivity, bridge tolerance, and the raster codes `DRY=0, FLOODED=1, UNKNOWN=255`.
- **Adding a flood.** A new flood is a new region file, not a code change. Thresholds are deliberately never tuned per region.
- **Paths.** All file locations come from `config.Paths`, with the layout `<data>/raw`, `processed`, `results` and `app`. Use it; don't hard-code paths.

### Data flow

```
pipeline/01..04  study area, Sentinel-1 flood rasters (Otsu, −26..−12 dB, 3 dB change rule, NASADEM slope mask),
                 OSM roads/villages/shelters, population, bridges, GPM IMERG rain   → <data>/processed/
pipeline/05..07  cut roads (share of 20 m check-points flooded) → isolation per date → timeline  → <data>/results/
pipeline/08      app package                                                         → <data>/app/
scripts/build_pwa.py   every data/*/app (+ analyses, NISAR, monitor) → pwa/public/data/<region-id>/
```

- `scripts/run_engine.py` reruns steps 02e–08 once the inputs exist.
- **Isolation is solved twice per date:**
  - once with only the roads seen open;
  - once with every road not seen cut.

  This yields connected, isolated or uncertain. Missing radar data must widen the answer, never be filled from another date.
- **Streamlit app** (`app/streamlit_app.py`): lists every `data/*/app` folder as a flood.
- **PWA** (`pwa/src/services/data.js`): reads only the static files in `public/data/`. It needs no backend for the flood results and works offline through the service worker (`pwa/src/sw.js`).
- **Generated output, not in git:** `pwa/public/data/` and `pwa/dist/`.

### Other components on top of the results

These read pipeline results and write next to them. They don't change the core results.

- **Planning analyses:** `scripts/road_criticality.py`, `relief_prepositioning.py` and `building_exposure.py`.
- **NISAR:** `scripts/nisar_polarization.py` and `nisar_village_water.py`, writing to `data/<region>_2026/results/nisar/`.
  - Two GCOV products exist: `NISAR_L2_GCOV_PROVISIONAL_V1` up to 16 Oct 2026, and the validated `NISAR_L2_GCOV_V1` from 21 Oct 2026.
  - Each scene records which product it came from. Scenes from different products or orbit tracks are not directly comparable.
  - The outer 4 km of each frame is excluded.
- **Automated watch:** `safewindow/watch.py` and `scripts/watch.py`.
  - Signals vote per village: satellite water change, GloFAS discharge forecast, a Random Forest river-flow model, Open-Meteo rain, and an optional AI reader (Gemini or any OpenAI-compatible API).
  - At least two independent signals must agree, and the level is the second-highest vote. The AI reader can never raise an alert alone.
  - The output is **draft/pending** alerts only.
- **Alerts:** `safewindow/alerts.py`, `scripts/send_alert.py`, `app/admin_app.py`.
  - Every alert goes draft → approval → send → cancel/expire, and every step is logged.
  - Test alerts are SIMULATION and go to registered test phones only.
- **Rescue platform:** the PWA pages `/rescue`, `/ngo` and `/gov`. There is no server of its own (Firebase Spark plan), so roles, the privacy split (shared / exact location / extra-care documents), allowed state transitions and version-checked claiming are all enforced in `firestore.rules`. Change the rules and `pwa/rules-tests/` together. The government role is a custom claim set only by `scripts/provision_government.py`.
- **GitHub Actions:**
  - `daily-check.yml` looks for new Sentinel-1 images and IMERG rain into `data/monitor/`. It is currently disabled in the Actions tab.
  - `watch.yml` runs by hand only. It reads flood maps from the published app (`--data-url`).

## Rules that are easy to break

- **Wording is tested.** `tests/test_pwa_texts.py` fails if `pwa/src/locales/{bn,en}.json` contain promising words such as "safe route", "road cut", "relief deadline", "নিরাপদ পথ", "রাস্তা কাটা" or "ত্রাণ পৌঁছানোর".
  - Use "possibly flooded road", "last seen passable", "supplies may run out (estimate)" and "possible route, not checked on the ground".
  - Both locale files must have the same keys and placeholders.
  - Bangla is the default language.
  - The Streamlit apps use the separate `locales/` folder.
- **Do not overwrite `data/live`.** It holds the 2022 study results and the submission evidence. `10_build_live_data.py`, `--no-slope-mask` and the hindcast refuse to write there. Write rebuilds and experiments to `data/rerun/` or `data/experiments/`, which are not in git.
- **No invented or interpolated data.** A date the radar did not see stays unknown/grey. An Otsu failure is recorded as such. Synthetic data (`data_demo/`, the `safewindow/forecast.py` demo) must stay labelled as synthetic.
- **Real alerts are off by default.** Sending to non-test phones needs `SAFEWINDOW_ALLOW_LIVE=1`. The watch's unvalidated forecast additionally needs `SAFEWINDOW_ALLOW_UNVALIDATED_FORECAST=1`. Keep both gates.
- **Secrets stay outside the repo.**
  - The Firebase Admin key comes from `GOOGLE_APPLICATION_CREDENTIALS` (`FIREBASE_ADMIN_KEY_JSON` on GitHub).
  - The Earth Engine service key comes from `EE_SERVICE_ACCOUNT_KEY`.
  - The AI key is read only from `GEMINI_API_KEY`.
  - `pwa/src/firebaseConfig.js` is the public web config, not a secret.
- **Git LFS** stores images, `.npz` and `.pt` files (see `.gitattributes`). `app/static/world/**` is marked `-text` because its manifest stores SHA-256 hashes, so line-ending changes would break it.
- **Run outputs.** `data/watch/*.json` is rewritten by every watch run. Don't commit it as part of unrelated changes.
- **Keep the README in step.** It quotes exact numbers (test counts, NISAR dates, IoU ranges). When a change moves one of them, update the README too.
