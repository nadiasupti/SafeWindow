# SafeWindow

**When does a village lose its last road to a flood shelter, and how long can it hold out?**

SafeWindow turns satellite flood maps into a date-based isolation timeline for every village. It combines Sentinel-1 radar flood maps, OpenStreetMap roads and shelters, NASA rainfall and elevation data, and a household supply assumption. For each village, it answers three questions:

1. **When** is the village cut off from every shelter? (a date range between radar passes)
2. **When was its road last seen passable**, and which route to a shelter was possible then?
3. **When may household supplies run out** (an estimate), given how many days of food a household has?

The method was built on the 2022 Sunamganj flood in Bangladesh. With no thresholds changed, it was then tested on the 2024 Sunamganj flood and on the 2025 Chenab–Jhelum flood at Trimmu, Pakistan.

NASA-ISRO **NISAR** L-band radar checks the flood maps independently, follows the 2026 monsoon through both polarizations (HH and HV), and shows the water under crops that C-band misses.

The results reach people through a **mobile app** at **https://safewindow-3b759.web.app**: installable, offline, Bangla and English, with approved village alerts. Around it sit:
- an **admin panel** where every alert is drafted, checked, approved and logged;
- a **rescue platform** for citizens, NGOs and government, with privacy and role rules enforced on the server;
- an **automated watch** that combines satellite water, river and rain forecasts and an optional AI reader into draft alerts;
- a **daily check** on GitHub Actions;
- **planning analyses:** roads that are a village's only link, where relief stock could wait before a flood, and 71,711 mapped buildings ranked for field checks.

> **Important:** SafeWindow is a research prototype. It is not an official warning system, evacuation planner, emergency service or decision tool, and it never says that help is on its way. Always follow official alerts (for example BMD, FFWC and DDM in Bangladesh, or NDMA and PDMA Punjab in Pakistan).

NASA Space Apps Challenge 2026 · Challenge: **Dancing with the SARs** · Team DeltaSentinels · MIT licence

---

## Contents

- [Results at a glance](#results-at-a-glance)
- [How it works](#how-it-works)
- [The mobile app](#the-mobile-app)
- [Rescue platform: citizens, NGOs and government](#rescue-platform-citizens-ngos-and-government)
- [Automated watch and river forecasts](#automated-watch-and-river-forecasts)
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

The same code and the same thresholds were used for all three floods. Nothing was tuned on any reference map. A fourth flood, Bara-Parsa in Nepal (2017), runs in the app as an unvalidated demonstration (see Detailed results).

| | Sunamganj 2022 | Sunamganj 2024 (unseen year) | Trimmu, Pakistan 2025 (unseen country) |
|---|---|---|---|
| Sentinel-1 dates (unclassifiable) | 19 (4) | 24 (5) | 9 (0) |
| Agreement with an independent satellite (IoU) | 0.81–0.84, same day (Chaohu-1, RCM-1) | 0.74 SAOCOM (−7 d); 0.69 Pleiades (+3 d) | 0.53 ICEYE (+1 d) |
| Same Sentinel-1 data, another agency's method (IoU) | 0.89 (UNOSAT) | 0.91 (UNOSAT, total water) | 0.68 (Copernicus EMS) |
| Precision against independent sensors | 0.93–0.95 | 0.85–0.97 | 0.48–0.73 |
| Villages isolated at the 20% cut threshold | 5 of 16 | **the same 5 of 16** | 2 of 26 (7 at the 10% threshold) |
| Dated news reports of cut roads | 2 of 2 match | 1 of 1 matches | 1 not visible (narrow man-made breaches) |

- **The same five villages** (catchment population about 187,800) are isolated in both Sunamganj floods, at every threshold tested.
- **NASA-ISRO NISAR** (L-band radar) sees 94.7–97.8% of SafeWindow's flood as water, in both countries, from an independent satellite and radar band (HH; with the outer 4 km of each NISAR frame left out, where the signal fades). In the app's NISAR page both polarizations, HH and HV, can be compared with Sentinel-1 using a swipe line.
- **Weaker at Trimmu.** Agreement is lower there, where the flood doubled within two days, irrigated rice may look like flood, and OpenStreetMap is thin.

**NISAR through the 2026 monsoon** (details under [NASA-ISRO NISAR](#nasa-isro-nisar-polarizations-the-monsoon-season-and-hidden-water)):
- **The haor drains.** On one NISAR orbit track over Sunamganj (track 069, every 12 days), HV water falls from 642 km² in June to 503 km² on 16 October.
- **Newest NISAR data.** Four passes from NASA's validated NISAR product (`NISAR_L2_GCOV_V1`, released from 21 October 2026) extend Sunamganj to 9 November 2026. They are kept apart from the season series: the product changed, and three of them are on other orbit tracks.
- **HV is the more robust polarization here.** It gives a water map on all 18 NISAR dates; HH does on 7. When both work they agree (IoU 0.63–0.93).
- **Water under crops.** Around Trimmu's villages NISAR sees a median 37 points more water than Sentinel-1 on 12 July, when the rice paddies are flooded for transplanting.

**Planning analyses** (from the same results, nothing re-tuned; details under [Planning analyses](#planning-analyses-road-criticality-and-relief-pre-positioning)):
- **Only connecting roads.** During the floods, connected villages often hang on a single road: on 29 May 2024, about 152,800 people; on 19 June 2024, about 230,700.
- **Relief pre-positioning, learned on 2022 and tested on 2024.** Three sites chosen from 2022 alone were within 5 km (straight line) of 4 of the 5 villages isolated in 2024, about 174,400 of 187,800 people, against about 35,800 for random sites. Both floods isolated the same villages, so this shows that isolation recurs; it is not an independent test.

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
        isolation date range, last seen passable, supply estimate
                         │
                         ▼
        mobile app (PWA) · admin alerts · Streamlit app · planning analyses
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
4. **Timeline.** Isolation dates are ranges between radar passes. The supply estimate ("household supplies may run out") is the earliest possible isolation date plus the household supply days (default 7, adjustable from 2 to 14 in the app). It is an estimate for planning, not a relief arrival date.

Full method, assumptions and benchmark design: [data/live/science_methods.md](data/live/science_methods.md).

---

## The mobile app

The app for villagers is a Progressive Web App in [pwa/](pwa/) (React and Vite), hosted on Firebase. Open **https://safewindow-3b759.web.app** on a phone and choose "Add to Home screen". It needs no account.

| Screen | What it shows |
|---|---|
| Home | Your village's status on the chosen radar date, three key facts from the data, quick links, the latest alert, what to do now, the whole area, and how fresh the data is |
| Map | Flood image, possibly flooded roads, the possible route (not checked on the ground), shelters (not verified), your location (stays on the phone), and optional analysis layers |
| Village | What was seen when (last seen passable, isolation range, first seen isolated), the supply estimate, the route, road dependence, and the status on every radar date |
| Emergency | A large call button (numbers from the region file), help by SMS, the nearest clinic, what to take, what to do before, during and after |
| Settings | Language, village, supply days, offline download, notifications, GPS permission, install |
| Analysis | Flood replay, only connecting roads, relief pre-positioning, mapped buildings with a field-verification ranking, and the daily watch, for planners and judges |
| NISAR | NASA-ISRO L-band radar for the 2026 monsoon: Sentinel-1 vs NISAR, HH vs HV and a colour composite, side by side with a swipe line; water over the season, agreement, water only NISAR sees around each village, and why L-band sees more water (paddies) |
| Account | Sign in or create an account; the profile button next to the alert bell shows the signed-in person (a shield marks a government account) |
| Rescue, NGO, Government | The rescue platform (next section); these pages load only when opened, so the village app stays light and offline-first |

- **Flood replay.** Previous, Play/Pause and Next on the date slider step through the real radar dates only. Each date shows how much the radar saw. A date the radar did not see shows a grey map and says so; it is never filled from another date.
- **Offline.** "Download this area's map" stores the flood's data on the phone. The map is drawn from the flood's own road network, so it works in airplane mode. Fonts and icons are bundled.
- **Alerts.** "Get alerts for this village" stores only the phone's notification address and the village (anonymous sign-in; Firestore rules let a phone read and write only its own entry). Alerts arrive even when the app is closed, are kept on the phone, and open the village page.
- **Wording.** The app says "possibly flooded road", "last seen passable", "supplies may run out (estimate)" and "possible route, not checked on the ground". It never says "safe route" or gives a relief arrival time.
- **Languages.** Bangla (default) and English, switched in the top bar.

Alerts are written and approved in a separate **admin panel** (`app/admin_app.py`) that opens only on the admin's own computer and needs the Firebase Admin key, which is kept outside the repository. Every alert goes through draft, approval (with a "source and date checked" box), sending, and cancellation or expiry, and every step is logged. Test alerts are marked SIMULATION and go only to registered test phones. The 🔔 Test notification tab sends one with a single click to the test phones that have alerts on for a chosen village (logged as Demo, valid for 6 hours). Real alerts stay switched off unless `SAFEWINDOW_ALLOW_LIVE=1` is set.

A **daily check** runs on GitHub Actions at 06:00 Bangladesh time ([.github/workflows/daily-check.yml](.github/workflows/daily-check.yml)): it looks for new Sentinel-1 images and NASA GPM IMERG rain over the monitored 2026 regions and writes `data/monitor/`. Rain is counted only for complete days (all 48 half-hour images), so a day NASA has not finished publishing is never under-counted. It sends no alert and does not turn rain into a forecast.

---

## Rescue platform: citizens, NGOs and government

A role-based response layer on top of the village app. The flood results, the village screens and the village alerts are unchanged by it.

| Who | Page | What they can do |
|---|---|---|
| Anyone | `/account` | Create an account or sign in (email and password) |
| Citizen | `/rescue` | Ask for help: location (GPS or typed), people, urgency, hazards and needs, with two separate consents for sharing exact location and extra-care details; follow the request's progress |
| NGO team | `/ngo` | Apply for registration; once government approves, see the open queue (rounded area only), accept a request and report each step (preparing, set out, arrived, rescued or help delivered, unable to reach, referred), and keep a list of resources (boats, vehicles, food, medical supplies) |
| Government | `/gov` | Overview and map, request list with filters, assign or reassign to an approved NGO, change priority, close, mark duplicate, reject or cancel (always with a reason), approve or suspend NGOs, and publish official alerts that appear on everyone's Home screen |

**Built with no server of its own.** The project runs on Firebase's free plan, so every rule is enforced in [firestore.rules](firestore.rules), not in the screens:
- **Roles.** Government is a server-side claim set only by `scripts/provision_government.py` with the Firebase Admin key; there is no public government sign-up. An NGO member belongs to an organisation that government has approved; suspending it removes access at once.
- **Privacy split.** A request is three documents: the shared part (area rounded to about 1 km, people, urgency, needs), the exact location and phone, and the extra-care details. An NGO reads the private parts only for a request assigned to it, while it is active, and only with the citizen's consent. Other citizens read nothing.
- **Controlled states.** Only listed moves are allowed, by role. Setting out is not the same as rescuing: an NGO cannot jump from "set out" to "rescued".
- **Safe claiming.** Every change carries a version number, so if two NGOs accept the same request, one write wins and the other is refused.
- **Honest wording.** Every rescue screen says the platform does not contact emergency services and never says a rescue is on its way unless a team reported it.

**Set up (once):** enable Email/Password sign-in in the Firebase console (keep Anonymous on for village alerts), publish the rules with `firebase deploy --only firestore:rules`, then sign up in the app and run `python scripts/provision_government.py <email>` on the administrator's computer.

---

## Automated watch and river forecasts

**The watch** (`safewindow/watch.py`, `scripts/watch.py`) runs without a person and ends in **draft** alerts for the admin. Each signal votes per village (none, watch, warning or critical):

| Signal | Source |
|---|---|
| Satellite | SafeWindow's own measurement: the share of the area within 3 km of the village that Sentinel-1 shows as water, against the previous pass |
| River | Open-Meteo Flood API (GloFAS, free): the forecast rise in river discharge near the village (a modelled value, not a gauge reading) |
| River-flow model | A Random Forest trained on 29 years of discharge and rain (the winner of the benchmark below); counted together with the river forecast, because both come from the same data |
| Rain | Open-Meteo: forecast rain here and upstream over the next 3 days |
| AI reader (optional) | Google Gemini, or any OpenAI-compatible API, reads the two satellite images and the measured numbers and gives each village a risk and a short reason |

- **At least two independent signals must agree.** The level is then the second-highest vote, the cautious choice. The AI reader is one vote and can never raise an alert alone.
- **The thresholds are working assumptions, not validated values.** So the watch's alerts are SIMULATION (test phones only). Real phones need two deliberate switches, `SAFEWINDOW_ALLOW_LIVE=1` and `SAFEWINDOW_ALLOW_UNVALIDATED_FORECAST=1`.
- **The AI key never touches a file.** It is read only from `GEMINI_API_KEY` in the user's environment. Several Gemini models are tried in turn, in case one is busy or retired. `python scripts/watch.py --check-ai` tests the key with one tiny request and reports the reason if it fails, without showing the key.
- **It can run on GitHub Actions** with the "Run workflow" button ([.github/workflows/watch.yml](.github/workflows/watch.yml); no schedule for now, the file says how to add one). It reads the flood maps from the published app, saves the flagged villages as **pending** alerts and sends nothing to any village. A village is not drafted again for the same satellite date (even after the admin rejected it) unless its level rises. It needs the repository secret `FIREBASE_ADMIN_KEY_JSON` (the Firebase Admin key file's text); `GEMINI_API_KEY` is an optional second secret for the AI reader.
- **The admin is told.** When new alerts wait for approval, the phones registered as admin phones (`python scripts/send_alert.py --add-admin-device <id>`, or the admin panel's phones tab) get one notification with the number of alerts and the villages. It is shown, not kept as a village alert. The admin panel also shows a banner while alerts wait. The admin then opens the ✅ Approval tab and publishes each alert (after ticking "source and date checked") or rejects it with a reason.

**Which forecasting method is most accurate?** (`scripts/benchmark_forecasts.py`, results in `data/benchmark/`). We tested 24 methods on four rivers (Surma at Sunamganj, Brahmaputra at Kurigram, Chenab at Trimmu, a small Terai stream at Bara-Parsa) at 1, 3 and 7 days ahead. The data was 29 years of free GloFAS discharge and ERA5 rain, and the test years were 2020–2025, which no model saw in training.
- **Tree ensembles came first.** Random Forest and Extra Trees led, with GRU/LSTM networks and gradient boosting close behind. The top ten are practically tied (NSE within about 0.01).
- **Accuracy falls with the horizon.** 1 day: NSE about 0.95, errors about 2%. 3 days: NSE about 0.93. 7 days: NSE about 0.82.
- **Flood peaks are not reliably predicted beyond 1–2 days.** On high flows only, NSE is about 0.7 at 1 day, 0.1 at 3 days and negative at 7 days. So the watch lets the 1-day forecast vote up to Warning, the 3-day forecast only Watch, and never Critical.
- **Transformers did not win** with about 7,000 training days per river. A pretrained Chronos model and ARIMA were below "tomorrow is like today".

**A separate demo** (`safewindow/forecast.py`, the admin panel's Forecast tab) shows how a rain-based model would feed the same approval flow. It is trained on **synthetic** data, is labelled as such in every message, and is never used by the watch.

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

**The mobile app** also needs [Node.js](https://nodejs.org) 20 or newer (tested with 24): `cd pwa`, then `npm install`. Deploying it needs the Firebase CLI (`npm install -g firebase-tools`) and access to the Firebase project.

**Accounts.** You need these only to rebuild data; the app runs without them.

| Account | Needed for | Setup |
|---|---|---|
| [Google Earth Engine](https://earthengine.google.com) (free, non-commercial) | Sentinel-1, NASADEM, GPM IMERG, WorldPop | `earthengine authenticate`, then `$env:EE_PROJECT="your-project-id"` |
| [NASA Earthdata](https://urs.earthdata.nasa.gov) (free) | OPERA DSWx-S1, NISAR, MCDWD | Log in once with `python -c "import earthaccess; earthaccess.login(persist=True)"` |

---

## Quick start

**Open the mobile app.** On a phone, open https://safewindow-3b759.web.app. To run it on your computer from the repository:

```powershell
python scripts/build_pwa.py          # export data/*/app (and the analyses) into pwa/public/data/
cd pwa
npm install
npm run build
npm run preview                      # http://localhost:4173
```

**Open the research app (Streamlit) with the real results.** No accounts are needed.

```powershell
python -m streamlit run app/streamlit_app.py
```

The app opens at http://localhost:8501.
- **Choose a flood** in the sidebar: Sunamganj 2022, Sunamganj 2024 or Trimmu 2025.
- **Replay the flood** with the date slider.
- **Click a village** to see its isolation range, the route last seen passable and the supply estimate.

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

### Mobile app, alerts and daily check

| Task | Command |
|---|---|
| Export every flood package, the analyses and the daily check into the app | `python scripts/build_pwa.py` |
| Build the app (from `pwa/`) | `npm run build`; check the code with `npm run lint` |
| Publish the app (Firebase Hosting, project in `.firebaserc`) | `firebase deploy --only hosting` |
| Remake the app icons and header logo from `pwa/brand/` | `python scripts/make_pwa_icons.py` |
| Open the admin panel (Windows; Admin key outside the repository) | `run_admin.bat`, then http://127.0.0.1:8502 |
| Send a SIMULATION alert to test phones only (`--dry-run` shows it without sending) | `python scripts/send_alert.py --simulation --flood sunamganj_2022 --village <id> --level warning --reason isolated --radar-date 2022-05-23` |
| Register or list test phones (the id is in the app's Settings) | `python scripts/send_alert.py --add-test-device <id>`, `--list-test-devices` |
| Run the daily check by hand (Earth Engine) | `python scripts/daily_check.py` |

| Variable | Meaning |
|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to the Firebase Admin key (admin panel and `send_alert.py`). Never put it in the repository. |
| `SAFEWINDOW_ALLOW_LIVE` | Set to `1` to allow real (non-simulation) alerts. Off by default. |
| `EE_SERVICE_ACCOUNT_KEY` | Path to an Earth Engine service-account key, for the daily check without a browser login. On GitHub it comes from the secret `EE_SERVICE_ACCOUNT_KEY_JSON`. |

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
| 07 | Isolation timeline, last-seen-passable dates and supply estimates | `python pipeline/07_timeline.py` |
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
| Run the test suite | `python -m pytest -q` |

### NASA data comparisons

| Task | Command |
|---|---|
| NASA-ISRO NISAR water vs SafeWindow ‡ | `python scripts/nisar_compare.py <out dir> --pair <NISAR date>:<NISAR baseline date>:<SafeWindow date>` |
| NISAR in HH and HV, compared with each other and with Sentinel-1, plus the app's NISAR layers ‡ | `python scripts/nisar_polarization.py sunamganj_2026 --dates 2026-06-18 2026-06-20 2026-07-24` (then `build_pwa.py`) |
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

### Planning analyses

They read only the pipeline's results and write new files next to them in `results/`; nothing else changes. Run `python scripts/build_pwa.py` afterwards to show them in the app.

| Task | Command |
|---|---|
| Only connecting roads, for every flood package (dry network and each radar date) | `python scripts/road_criticality.py` (or one package: `python scripts/road_criticality.py data/live`) |
| Relief pre-positioning, learned on one flood and tested on a later one | `python scripts/relief_prepositioning.py --train data/live --test data/sunamganj_2024 --k 3 --radius-km 5` |
| Mapped buildings: download Google Open Buildings (Earth Engine, personal login), then road access and nearness to water per building and date | `python scripts/building_exposure.py fetch data/live`, then `python scripts/building_exposure.py run` (run `road_criticality.py` afterwards to add building counts to the critical roads) |

### NISAR, buildings, rescue platform and watch

| Task | Command |
|---|---|
| NISAR HH and HV for chosen dates, the app's NISAR layers (Earthdata login) | `python scripts/nisar_polarization.py sunamganj_2026 --dates 2026-06-18 2026-07-24` |
| Water only NISAR sees, around each village (no download) | `python scripts/nisar_village_water.py` |
| Mapped buildings: download (Earth Engine), then analyse | `python scripts/building_exposure.py fetch data/live`, then `python scripts/building_exposure.py run` |
| Give an account the government role (Firebase Admin key) | `python scripts/provision_government.py <email>` |
| Automated watch, now or replaying a past day | `python scripts/watch.py --flood sunamganj_2024`, or add `--as-of 2024-06-17` |
| Check the AI key and model | `python scripts/watch.py --check-ai` |
| Watch and put pending alerts in front of the admin (tells the admin phones) | `python scripts/watch.py --flood sunamganj_2024 --drafts --by "Name"` |
| Register or list admin phones (told when alerts wait for approval) | `python scripts/send_alert.py --add-admin-device <id>`, `--list-admin-devices` |
| River-flow forecast for each river | `python scripts/flow_forecast.py` |
| Forecast benchmark (24 methods; `pip install -r requirements-benchmark.txt`) | `python scripts/benchmark_forecasts.py fetch`, `run`, `report` |
| The app's own tests, and the security-rule tests (Firebase emulator) | `cd pwa; npm test`; `cd pwa/rules-tests; npm test` |

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

| Village | Isolation | Last seen passable | Supplies may run out (estimate, 7 supply days) |
|---|---|---|---|
| Paschim Birgaon | on or before 16 May | none observed | 23 May |
| Dholkotob | between 17 and 23 May | 16 May | 24 May |
| Patharia | between 17 and 23 May | 16 May | 24 May |
| Boromuha | on or before 23 May | none observed | 30 May |
| Purba Birgaon | on or before 23 May | none observed | 30 May |

The same five villages are isolated at the 10%, 20% and 40% thresholds. The village dates have not been checked against reports about specific villages.

**Rule update, 24 October 2026.** On 4 of the 19 dates, Otsu finds no dark-water threshold, typically because wind-roughened haor water is not dark. Those maps are now unknown instead of being classified with a fixed −18 dB, which caught almost no water. This moved some isolation and last-seen-passable dates. It did not change the five isolated villages, their population, the benchmark scores or the news checks. The check is `scripts/otsu_fallback_check.py`.

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

### August 2017, Bara-Parsa, Nepal (demonstration only)

A demonstration that the unchanged method runs in a third country (`regions/nepal_terai_2017.yaml`, 152 OpenStreetMap villages). It is shown in the mobile app, marked as a demonstration.

- Only 3 of 8 Sentinel-1 dates could be mapped (16, 20 and 28 August). The flood peak (11–14 August) was missed, so the pipeline's own check says NO-GO and there is no map from before the peak.
- The study area was chosen where the radar showed the most flood water.
- It is **not validated**: there is no independent flood map or road report for it, and the shelters are unverified OpenStreetMap candidates. It is not counted in any result above.

### What NASA data adds (measured)

| NASA data | Test | Result |
|---|---|---|
| **NISAR** (NASA-ISRO, L-band) | SafeWindow's flood vs NISAR water, 1–3 days apart, Sunamganj and Trimmu 2026, in HH and HV | 94.7–97.8% of SafeWindow's flood is also water in NISAR HH. HV gives a water map on all 18 dates; HH on only 7 (its threshold falls outside the rule on 11). NISAR also sees water under crops, which SafeWindow intentionally does not count. |
| **OPERA DSWx-S1** | Both maps against the same Copernicus EMS references, Trimmu 2025 | Where SafeWindow and OPERA agree, 84–92% of the flood is confirmed by EMS. This gives a high-confidence class. |
| **GPM IMERG** | Which rain window best tracks the flooded area | Upstream rain leads the flood by about 5 days at Trimmu, and by 0–3 days in the haor. Exploratory: about 9 radar dates per flood. |
| **NASADEM** slope mask | Benchmark with and without the mask, 3 floods | In these flat floodplains the mask lowers IoU by 0.006–0.054. Kept unchanged, to avoid tuning on test data. |
| **NASADEM** vs Copernicus GLO-30 | Redrawing observed floods from DEM height | No clear difference |
| **LANCE MCDWD** | Archive search | Only the last ~7 days are kept, so it is unusable for past floods |

### NASA-ISRO NISAR: polarizations, the monsoon season and hidden water

NISAR science data is public from 17 June 2026, so this uses the 2026 monsoon over the same two study areas (`regions/sunamganj_2026.yaml`, `regions/punjab_trimmu_2026.yaml`).

**How.** Each NISAR GCOV granule is about 6.5 GB, so only the HH and HV chunks over the study area are read over HTTPS (`scripts/nisar_polarization.py`). Each polarization gets the same Otsu rule as Sentinel-1; nothing is tuned for NISAR or HV. Within 4 km of a frame's no-data edge the signal fades towards the noise floor (about −47 dB at the edge) and looks like water, so that strip is left out on every date.

**Agreement with Sentinel-1** (the Sentinel-1 map within 3 days that saw the most of the area):

| Area, NISAR date | Sentinel-1 | Share of Sentinel-1's water also water in NISAR HH / HV |
|---|---|---|
| Sunamganj, 20 Jun | 19 Jun | 96.1% / 85.5% |
| Sunamganj, 30 Jun | 28 Jun | 97.8% / 99.0% |
| Sunamganj, 24 Jul | 22 Jul | 97.0% / 98.6% |
| Sunamganj, 18 Jun and 12 Jul | 19 Jun, 10 Jul | no HH map / 98.8%, 97.0% |
| Trimmu, 24 Jul | 25 Jul | 94.7% / 96.8% |
| Trimmu, 12 Jul | 13 Jul | no HH map / 89.2% |

**The season (Sunamganj, track 069, every 12 days).** HV water: 642 km² (18 Jun), 655 (30 Jun), 638 (12 Jul), 656 (24 Jul), 639 (17 Aug), 633 (29 Aug), 623 (10 Sep), 583 (22 Sep), 552 (4 Oct), 503 (16 Oct). The haor stays full through the monsoon and drains from September. HH gives a map on only 7 of the 18 NISAR dates in both areas, because its threshold falls outside the rule's range; HV does on all 18.

**Newest passes (validated product V1, 21 October to 9 November 2026).** HV water: 779 km² (21 Oct, track 141), 813 (30 Oct, track 091), 805 (2 Nov, track 141) and 554 (9 Nov, track 069). Tracks 141 and 091 cover the whole study area, while track 069 loses about 152 km² at its frame edge, so only track 069 can be set beside the series above. There, 9 November (554 km²) is higher than 16 October (503 km²), yet almost no rain fell in early November (under 1 mm a day). The HV threshold is the same (−18.9 dB), but HH backscatter is about 1 dB lower in the new product, so the change is more likely the product (or fields flooded for winter rice) than a new flood. None of these four dates has a Sentinel-1 map within 3 days.

**Water only NISAR sees, around each village** (`scripts/nisar_village_water.py`). L-band (about 24 cm) passes between plants; C-band (about 6 cm) stops at the leaves. So where NISAR sees water and Sentinel-1 does not, the likeliest cause is water under vegetation.
- **Trimmu, 12 July:** the median village has 37 points more water within 3 km in NISAR than in Sentinel-1. The largest gaps are 45–62% water in NISAR against 2–3% in Sentinel-1, when the kharif rice paddies are flooded for transplanting.
- **Sunamganj:** the gap is 11–18 points.
- This measures a gap; it does not say whether the cause is paddy, flooded grass or something else, and there is no field data.

In the app, the NISAR page shows every layer with a swipe line, the season as a chart and the village gaps for the chosen date.

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

### Planning analyses: road criticality and relief pre-positioning

Both read the pipeline's results and change none of them (`safewindow/criticality.py`, `safewindow/prepositioning.py`).

**Only connecting roads.** A road segment matters on its own only if closing it splits the network so that some villages have no road path left to any shelter. Segments that would strand the same villages are reported together as one stretch. The test runs on the dry network (every mapped road open) and on the roads seen open on each radar date; a village that is connected but hangs on such a segment is *fragile* on that date. The method was checked against brute force on 40 random networks and against the pipeline's own reachability on 190 real Sunamganj 2022 segments (190 of 190 agree).

| Flood | Dry network | During the flood (roads seen open) |
|---|---|---|
| Sunamganj 2022 | 3 stretches, each one village's own access road (0.1–0.4 km) | 6 villages fragile on some date; a 1,370-person village hung on 2.8 km of single road on several dates |
| Sunamganj 2024 | the same 3 stretches | 8 villages fragile on some date; about 152,800 people on 29 May and 230,700 on 19 June |
| Trimmu 2025 | 13 stretches; the largest strands 4 villages (about 223,000 people) behind 10.8 km of road | 16 villages fragile on some date |

OpenStreetMap roads are incomplete and the shelters are unverified, so this is a planning signal, not an engineering assessment.

**Relief pre-positioning (learned on 2022, tested on 2024).** From the 2022 flood only, a greedy choice of 3 shelter candidates covering the most people in isolated villages within 5 km (straight line). Then scored on the villages the 2024 flood isolated:

| Radius | People covered in 2024 (of 187,800) | 3 random sites (average) | Best any 3 sites could do, with hindsight |
|---|---|---|---|
| 3 km | 20,302 | 1,416 | 20,302 |
| **5 km** | **174,413** (4 of 5 villages) | 35,816 | 174,413 |
| 10 km | 187,800 | 101,163 | 187,800 |

- **Not an independent test.** 2022 and 2024 isolated exactly the same 5 villages, so the result shows that isolation recurs.
- **Straight line on purpose.** During the flood no open road joins an isolated village to any shelter (that is what isolated means). Stock has to reach the villages before their last-seen-passable date, or by boat, which the model does not know.
- The sites are unverified OpenStreetMap candidates. This is an analysis, not a decision.

**Mapped buildings (Google Open Buildings v3, confidence ≥ 0.75).** Each building gets the village rule: joined to its nearest road junction (more than 500 m away = far from roads), then connected, isolated or uncertain on each radar date; and whether mapped flood water lies within 50 m. Buildings on road fragments that OpenStreetMap does not join to any shelter even when dry are reported as "no mapped road link", not as isolated. Results are summed per 500 m cell for the app, and cells are ranked for field verification by building-dates seen isolated (`safewindow/buildings.py`, `scripts/building_exposure.py`).

| Flood | Mapped buildings | Most seen isolated on one date | Far from roads | No mapped road link |
|---|---|---|---|---|
| Sunamganj 2022 | 71,711 | 30,105 (18 June) | 866 | 3,752 |
| Sunamganj 2024 | 71,711 | 28,124 (11 July) | 866 | 3,752 |
| Trimmu 2025 | 126,977 | 7,999 (2 September) | 77,987 | 15 |

A mapped building is not a count of people. "Within 50 m of mapped water" is not "flooded inside": radar often misses water between buildings, and haor homes stand on raised ground. At Trimmu most buildings are more than 500 m from a mapped road, because OpenStreetMap's roads there are thin. The ranking says where to check first; it is not a rescue list.

---

## Repository layout

```text
SafeWindow/
├── pwa/                    Mobile app (React + Vite PWA): src/ (pages, components, services), public/
│                           (icons, logo), brand/ (original images), tests/ and rules-tests/ (security rules)
├── app/                    Streamlit app (streamlit_app.py), admin panel (admin_app.py, admin_text.py);
│                           floodnet_app.py is experimental
├── pipeline/               Numbered data pipeline, steps 01–10
├── safewindow/             Core library: region files, road cutting, isolation, timeline, validation,
│                           alerts, daily monitor, road criticality, relief pre-positioning, buildings,
│                           NISAR village water, automated watch, river-flow forecast, dispatch
├── scripts/                App export (build_pwa.py), alerts, daily check, planning analyses, NISAR,
│                           buildings, watch and forecasts, benchmarks, NASA comparisons, hindcast,
│                           government provisioning, demo and packaging tools
├── .github/workflows/      Daily check on GitHub Actions
├── firebase.json, firestore.rules, .firebaserc   Hosting and database rules for the mobile app
├── regions/                One YAML file per flood, plus benchmark reference lists
├── locales/                App text per language (en.json, bn.json)
├── tests/                  pytest suite
├── data/
│   ├── live/               Sunamganj 2022: results, benchmark, evidence (app default)
│   ├── sunamganj_2024/     Sunamganj 2024 results
│   ├── punjab_trimmu_2025/ Trimmu, Pakistan 2025 results
│   ├── nepal_terai_2017/   Bara-Parsa, Nepal 2017 (demonstration only, not validated)
│   ├── sunamganj_2026/     2026 monsoon: NISAR layers and results (results/nisar/), daily watch
│   ├── punjab_trimmu_2026/ 2026 monsoon: NISAR layers and results, daily watch
│   ├── monitor/            Daily check results (written by GitHub Actions)
│   ├── benchmark/          Forecast benchmark inputs and results (24 methods, 4 rivers)
│   ├── forecast/           River-flow models (flow/) and the synthetic demo model
│   └── watch/              The latest automated-watch report per flood
├── ml/                     Experimental machine-learning components
├── run_demo.bat            One-click synthetic demo (Windows)
└── requirements*.txt       Dependencies (app, pipeline, ML)
```

Some folders are created locally and are not in git:
- `data/sources/` holds the downloaded reference maps.
- `data/experiments/` and `data/rerun/` hold experiment and rebuild runs.
- `data_demo/` holds the generated synthetic demo.
- `pwa/public/data/` is generated by `scripts/build_pwa.py`, and `pwa/node_modules/` and `pwa/dist/` by npm.

---

## Data sources

All inputs are free and public.

### NASA and NASA-ISRO data

| Data | Provider | Used for |
|---|---|---|
| NISAR GCOV (L-band, HH and HV) | NASA-ISRO, via NASA Earthdata | Independent L-band check, the 2026 monsoon season, water hidden under crops around villages |
| OPERA DSWx-S1 | NASA JPL, via NASA Earthdata | Confidence comparison |
| GPM IMERG V07 | NASA | Daily rainfall, lag analysis, hindcast, daily check, automated watch |
| NASADEM | NASA | Slope mask |
| NASA POWER (daily rainfall) | NASA Langley | Rain feature in the forecast benchmark |
| LANCE MCDWD, MODIS MOD09GA | NASA | Tested; not usable for these floods (archive length, cloud) |

### Other data

| Data | Provider | Used for |
|---|---|---|
| Sentinel-1 GRD | ESA Copernicus, via Google Earth Engine | Flood maps |
| Copernicus GLO-30 DEM | ESA | Between-dates estimate |
| OpenStreetMap | OpenStreetMap contributors (ODbL) | Roads, bridges, villages, shelter candidates |
| WorldPop 2020 | WorldPop | Village catchment population |
| Google Open Buildings v3 | Google Research, via Google Earth Engine | Mapped buildings: road access, nearness to water, field-verification ranking |
| GloFAS river discharge | Copernicus Emergency Management Service, via the Open-Meteo Flood API | River-flow forecast, automated watch, forecast benchmark (a modelled series, not a gauge) |
| ERA5 and weather-model rainfall | ECMWF, via the Open-Meteo archive | Rain at each site and upstream, for the forecast and the watch |
| UNOSAT FL20220525BGD, FL20240502BGD | UNITAR-UNOSAT | Benchmarks (Bangladesh) |
| Copernicus EMS EMSR838 | European Commission | Benchmark (Pakistan) |
| News reports | The Daily Star, The Daily Observer, Dawn | Road-cut checks |
| ETCI 2021 (Sentinel-1 flood tiles), FloodNet (aerial images) | ETCI 2021 competition; FloodNet authors | Side experiments only (see Experimental components) |

The OpenStreetMap data is a snapshot from October 2026, used for all three floods.

### NASA and space-agency partner resources

| Resource | How SafeWindow uses it |
|---|---|
| NASA Earthdata (the catalog behind Earthdata Search) | NISAR, OPERA and MODIS data are searched and downloaded from it with the `earthaccess` Python library |
| ASF DAAC (Alaska Satellite Facility), NASA's SAR archive | Source of the NISAR GCOV data (`NISAR_L2_GCOV_PROVISIONAL_V1` to 16 October 2026, the validated `NISAR_L2_GCOV_V1` from 21 October) |
| NISAR Data User Guide (ASF) | Reference for reading the GCOV product's HH and HV backscatter layers |
| CSA RADARSAT Constellation Mission (RCM) | Indirect: UNOSAT flood maps made from RCM-1 images (18 and 19 June 2022) are benchmarks for Sunamganj 2022 (IoU 0.81–0.89) |
| CONAE SAOCOM | Indirect: UNOSAT flood and affected-road maps made from a SAOCOM L-band image (June 2024) are benchmarks for Sunamganj 2024 (IoU 0.74; 56–71% of the road SafeWindow cuts is on roads UNOSAT marks as flood-affected) |

SafeWindow did not download raw RCM or SAOCOM images; it compares its results with maps made from them.

Further reading on NISAR for floods (background, not data inputs): the NISAR Applications White Papers (two-page overviews of NISAR applications, including floods and disaster response) and the NISAR StoryMaps on SAR flood mapping, both listed in the Space Apps 2026 "Dancing with the SARs" challenge resources.

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
- **Notifications are not guaranteed.** Push messages need internet and can be held back by battery savers or phone settings; no new alert arrives while a phone is offline.
- **Planning analyses are signals.** Road criticality depends on OpenStreetMap's roads; the relief test repeats the same five villages and uses straight-line distance.
- **Mapped buildings are not people.** "Within 50 m of mapped water" is not "flooded inside": radar often misses water between buildings.
- **The watch and the forecasts are not validated** on real floods: their thresholds are working assumptions, river discharge is modelled, flood peaks are unreliable beyond 1–2 days, and the forecast demo uses synthetic data. Their alerts go to test phones only.
- **NISAR** covers only 2026 and has no independent flood map for those dates; the agreement figures compare two radars, not ground truth. Dates to 16 October use the provisional product and later dates the validated `NISAR_L2_GCOV_V1`; the earlier dates have not been reprocessed with V1, so water areas across the two products are not directly comparable.
- **The rescue platform** is a prototype on the free Firebase plan. It does not contact emergency services; multi-factor sign-in and agency sub-roles are not built.
- **Not for emergency use.** Results must not be used to make emergency decisions without official sources.

---

## Project status

**Complete:**
- real-region results for three floods in two countries;
- independent flood-extent benchmarks with confidence intervals;
- road checks against dated news reports;
- an independent NISAR radar check;
- a reproducibility check;
- a source manifest and a methods document;
- the mobile app (offline, Bangla and English, flood replay, village alerts), the admin panel with approval and log, and the daily check on GitHub Actions;
- the planning analyses (only connecting roads, relief pre-positioning);
- mapped buildings (Google Open Buildings) with road access, nearness to water and a field-verification ranking;
- NISAR in both polarizations over the 2026 monsoon, with water only NISAR sees around each village;
- the rescue platform for citizens, NGOs and government, with its rules enforced and tested on the server side;
- the automated watch, the river-flow forecast and a 24-method forecast benchmark;
- tests: 305 pytest tests, the app's own unit tests (14), security-rule tests against the Firebase emulator, and browser checks of the mobile app (main flow 34, flood replay 42, analyses 29, NISAR 29, buildings 21, profile 11).

**Open:**
- an independent scientific review;
- hand-verified shelter lists;
- a check of village isolation dates against field or news reports;
- running the full pipeline automatically when a new radar image arrives (the daily check only reports it);
- recorded Bangla voice messages.

Until a review is recorded, `scripts/verify_submission.py data/live` reports the release as unverified, by design.

---

## Experimental components

The `ml/` folder and `app/floodnet_app.py` are side experiments. No SafeWindow flood map, road cut, isolation date or benchmark score uses them. See [ml/README.md](ml/README.md).

- **FloodNet classifier** (`ml/floodnet_model.pt`). It labels a whole aerial photo as flooded or not, and is trained on the public FloodNet dataset.
- **Temporal U-Net** (`ml/model.pt`). It is trained only on the synthetic demo data and must not be used for real predictions.
- **ETCI flood segmentation** (`ml/etci_segment.py`, `ml/etci_model.pt`). A network trained on real Sentinel-1 VV/VH tiles from the ETCI 2021 dataset, split by whole scene and compared with a plain Otsu threshold.

---

## Use of AI

- **In the method:** none. Flood maps use an Otsu threshold and fixed rules; isolation uses graph shortest paths. Machine learning appears only in the automated watch (the river-flow model, and an optional AI image reader that is one vote among several and can never raise an alert alone) and in the experiments above.
- **In development:** the team used two AI assistants, ChatGPT (OpenAI) and Claude (Anthropic, through Claude Code), to review the repository, fix bugs, write analysis and test code, build the mobile app, and draft documentation. The team checked and decided on all of this work. Every result in this repository is produced by the repository's code and checked by its tests.

---

## Team and licence

**Team DeltaSentinels**, NASA Space Apps Challenge 2026: Farhan Labib , Nadia Yeasmin and Ashraf Uz Zaman .

The code is released under the MIT licence (see [LICENSE](LICENSE)). Data products keep the licences of their providers.
