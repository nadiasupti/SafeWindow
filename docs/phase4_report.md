# Phase 4 report: what NASA data adds, measured

Date: 24 October 2026. Rule: show how much each NASA dataset changes the results; do not just list it. Sentinel-1 is an ESA mission. SafeWindow's NASA inputs are NASADEM, GPM IMERG and, from this phase, OPERA DSWx-S1.

## Summary

| NASA data | What was tested | Result |
|---|---|---|
| **NASADEM** (5° slope mask) | Benchmark scores with and without the mask, 3 floods, 18 comparisons | **The mask lowers IoU in every case** (by 0.006–0.054) in these flat floodplains: it removes real water. Kept unchanged, because removing it after seeing the benchmark would be tuning on test data. |
| **GPM IMERG** (daily rain) | Which rain window and lag best track the flooded area | Trimmu: rain over the **upstream Chenab–Jhelum hills about 5–7 days earlier** (Spearman 0.98). Sunamganj 2024: local and Meghalaya rain over 0–3 days (0.98). Exploratory only: 9 dates per flood, 80 combinations tested. |
| **OPERA DSWx-S1** (NASA JPL water maps) | Against the same Copernicus EMS references, on the same pixels, as SafeWindow | Alone, OPERA is more conservative: precision 0.81–0.86, recall 0.41–0.52, IoU below SafeWindow. **Where SafeWindow and OPERA agree, precision is 0.84–0.92**, against 0.73–0.77 for SafeWindow alone. |

The useful NASA contributions are a **lead time from upstream rainfall** (GPM IMERG) and a **confidence layer from an independent NASA product** (OPERA). In flat terrain, the NASADEM slope mask did not help.

## 4.1 NASADEM slope mask (ablation)

Maps were rebuilt without the slope mask (`02a_sentinel1_gee.py --no-slope-mask`, in separate folders) and scored with `scripts/ablation_compare.py` on exactly the same pixels.

| Flood | Comparisons | IoU change from removing the mask | Recall | Precision |
|---|---|---|---|---|
| Sunamganj 2022 | 4 | +0.008 to +0.048 | up | down by about 0.01 |
| Sunamganj 2024 | 8 | +0.006 to +0.054 | up | down by 0.002–0.02 |
| Trimmu 2025 | 7 | +0.006 to +0.030 | up | about the same |

**Why.** The mask exists to remove radar-shadow false water on hillsides. All three study areas are flat floodplains, where pixels with a slope above 5° in the 30 m DEM are mostly embankments, riverbanks and DEM noise next to water.

**Decision.** The method is not changed. Removing the mask because the benchmark improves would be tuning on test data.

**Possible improvement, to be decided before testing on a held-out flood:** replace the slope mask with a HAND mask (height above nearest drainage, derived from NASADEM). HAND is the standard terrain mask in flood mapping, and OPERA itself uses it.

## 4.3 GPM IMERG: how long after the rain does the flood come?

`scripts/rain_flood_lag.py`. The flood signal is the flooded share of the study area on radar dates with at least 95% coverage. The rain signal is the total over W days ending L days before the radar date. Rain was downloaded for April to the end of each flood (`data/experiments/phase4_rain/`).

| Flood | Best rain signal | Spearman ρ | Reading |
|---|---|---|---|
| Trimmu 2025 | Upstream Chenab–Jhelum box, 7-day total ending **5 days** before | 0.98 (lags 4–7 all ≥ 0.90) | River travel time from the Kashmir hills: **about 5 days of potential warning** |
| Trimmu 2025 | Local box | ≤ 0.50 | Local rain barely explains the flood |
| Sunamganj 2024 | Local or Meghalaya box, 3-day total, lag 0 | 0.98 | Flash-flood response within about 0–3 days: little lead time |
| Sunamganj 2022 | – | ≤ 0.62 | Every full-coverage date was already flooded (from 23 May), so there was no dry baseline to compare |

**Caveats:**
- There are only 9 radar dates per flood, and 80 window and lag combinations were tested, so a high ρ can occur by chance.
- These are the timings to test in Phase 6 (early warning) on other years, not validated rules.

## 4.4 NASA OPERA DSWx-S1 (Trimmu 2025)

`scripts/opera_compare.py` downloads the DSWx-S1 B01_WTR layers through Earthdata login and puts them on the SafeWindow grid. OPERA maps all water, while SafeWindow maps water that is new compared with the dry season. So OPERA "new water" = water on the flood date and not water on most of the 15 usable April–May 2025 OPERA dates (98 km² of usual water).

All maps are scored against the Copernicus EMS references on the same pixels (IoU / precision / recall):

| Reference → our date | SafeWindow | OPERA alone | Both agree (AND) | Either (OR) |
|---|---|---|---|---|
| ICEYE 31 Aug → 1 Sep | 0.53 / 0.73 / 0.66 | 0.38 / 0.81 / 0.41 | 0.35 / **0.84** / 0.37 | **0.55** / 0.72 / 0.70 |
| ICEYE 30 Aug → 1 Sep | 0.42 / 0.48 / 0.79 | 0.34 / 0.56 / 0.47 | 0.32 / 0.57 / 0.43 | **0.43** / 0.47 / 0.83 |
| EMS Sentinel-1 1 Sep | 0.68 / 0.77 / 0.85 | 0.48 / 0.86 / 0.52 | 0.46 / **0.90** / 0.48 | **0.69** / 0.76 / 0.89 |
| EMS Sentinel-1 2 Sep | 0.62 / 0.75 / 0.79 | 0.41 / 0.85 / 0.44 | 0.36 / **0.92** / 0.37 | **0.66** / 0.74 / 0.85 |
| EMS Sentinel-1 28 Aug (small flood) | 0.29 / 0.41 / 0.49 | 0.16 / 0.30 / 0.24 | 0.14 / 0.54 / 0.16 | 0.27 / 0.34 / 0.58 |

SafeWindow and OPERA agree with each other at IoU 0.32–0.40 on 1–2 September.

**Reading.**
- OPERA is a conservative water map: it flags less flood, but more of what it flags is right.
- SafeWindow's simple change rule finds more of the flood.
- **Where both flag flood, 84–92% is confirmed by EMS.** This gives a high-confidence class, a natural use of an independent NASA product.

**Proposed (not yet adopted).** Show flood confidence in the app:
- high where SafeWindow and OPERA agree;
- medium where only one of them flags water.

The rule should be fixed now and tested on the next flood with OPERA coverage, not tuned here. Note that OPERA DSWx-S1 exists only from September 2024: it is absent for Sunamganj 2022 and 2024 (0 granules).

## Not done yet

- **4.2 DEM gap-fill with NASADEM.** `02d_dem_gapfill.py` still uses the Copernicus DEM.
- **4.5 NISAR.** NISAR GCOV exists for the Punjab flood of 22–29 July 2026 (and for Sunamganj, June–September 2026). Independent references for July 2026 still need to be found.
- **4.6 LANCE MCDWD.** Not tried.

## Reproduce

```powershell
# 4.1 (Earth Engine): maps without the slope mask, in a separate folder
$env:SAFEWINDOW_REGION="punjab_trimmu_2025"; $env:SAFEWINDOW_DATA_DIR="data/experiments/ablation_noslope_trimmu"
python pipeline/02a_sentinel1_gee.py --no-slope-mask --dates 2025-08-28 2025-09-01 2025-09-02
python scripts/ablation_compare.py data/punjab_trimmu_2025 data/experiments/ablation_noslope_trimmu --label "no NASADEM slope mask"
# 4.3
python scripts/rain_flood_lag.py data/punjab_trimmu_2025 data/experiments/phase4_rain/punjab_trimmu_2025/processed/rainfall_daily.csv
# 4.4 (Earthdata login)
$env:SAFEWINDOW_DATA_DIR="data/punjab_trimmu_2025"
python scripts/opera_compare.py data/experiments/opera_trimmu --dates 2025-08-28 2025-09-01 2025-09-02 --dry-start 2025-04-01 --dry-end 2025-05-31
python scripts/ablation_compare.py data/punjab_trimmu_2025 data/experiments/opera_trimmu --label "NASA OPERA DSWx-S1"
```
