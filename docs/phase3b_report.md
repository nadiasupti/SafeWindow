# Phase 3b report: Trimmu, Jhang, Punjab, Pakistan, August–September 2025

Date: 24 October 2026. Region file: `regions/punjab_trimmu_2025.yaml`. Outputs: `data/punjab_trimmu_2025/`. Event choice: [phase3b_event_selection.md](phase3b_event_selection.md).

**Setup.**
- **Method:** same code and thresholds as Sunamganj, with nothing tuned for Pakistan.
- **Study area:** the Copernicus EMS EMSR838 AOI 5 polygon (1,014 km²), via the new `area.boundary_file` option.
- **Radar:** 9 Sentinel-1 dates, 16 Aug–14 Sep 2025, all with 100% coverage.
- **Dry reference:** April–May 2025.
- **Map projection:** UTM 43N, set by hand because the area straddles 72°E (see section 5).

## 1. The flood seen by SafeWindow

Flooded share of the grid, by date:

| Dates | Flooded share of the grid |
|---|---|
| 16, 20, 21 and 28 Aug | 1–2% |
| **1 Sep** | **9.3% (about 230 km²)** |
| **2 Sep** | **9.3%** |
| 9 Sep | 8.7% |
| 13–14 Sep | 3% |

This timing matches the reports: Dawn expected more than 800,000 cusecs at Trimmu on 30 August, and Copernicus EMS mapped 20 km² of flood on 28 August, rising to 210–220 km² on 1–2 September.

## 2. Flood extent against Copernicus EMS (EMSR838 AOI 05)

`scripts/benchmark_region.py` with `regions/punjab_trimmu_2025_benchmark.yaml`. Parts of an image that EMS marked "Not Analysed - No data" are excluded.

| Reference | Tier | Our map (gap) | Area (km²) | IoU (95% CI) | Precision | Recall |
|---|---|---|---|---|---|---|
| ICEYE, 31 Aug 17:28 UTC | other radar (X-band) | 1 Sep (+1 d) | 858 | **0.533** (0.515–0.549) | 0.731 | 0.662 |
| ICEYE, 30 Aug 23:54 UTC | other radar (X-band) | 1 Sep (+2 d) | 789 | 0.424 (0.401–0.444) | 0.477 | 0.791 |
| ICEYE, 31 Aug | other radar | 28 Aug (−3 d) | 858 | 0.051 | 0.510 | 0.054 |
| EMS Sentinel-1, 1 Sep | same sensor | 1 Sep (0 d) | 1,014 | **0.680** (0.666–0.694) | 0.775 | 0.848 |
| EMS Sentinel-1, 2 Sep | same sensor | 2 Sep (0 d) | 1,014 | 0.625 (0.611–0.640) | 0.753 | 0.786 |
| EMS Sentinel-1, 28 Aug | same sensor | 28 Aug (0 d) | 908 | 0.290 (0.260–0.317) | 0.412 | 0.495 |

**Agreement is lower than in Sunamganj** (there: 0.81–0.89 in 2022, and 0.69–0.74 against independent sensors in 2024). Likely reasons:

- **The flood changed fast.** EMS's own flooded area doubled between 30 August and 1 September, so a gap of 1–2 days already costs agreement. Against the 28 August map, which was taken before the peak, recall is near zero.
- **Small flooded fraction.** On 28 August only about 2% of the area was flooded, and IoU is unstable for small extents.
- **Irrigated rice (a hypothesis, not tested).** The dry reference is April–May, when fields are bare. In August, kharif rice paddies hold water, and SafeWindow's change rule counts them as flooded. This fits the precision of 0.75–0.78 even against the same Sentinel-1 image. A pre-flood reference from the same season, or a crop mask, could address it. **It was not tested on the benchmark, to avoid tuning on test data.**

## 3. Village isolation

| Destinations | Isolated at the 20% / 40% threshold | Isolated at 10% |
|---|---|---|
| OSM shelter candidates (only **3**, all near Shorkot) | 2 villages, about 75,300 people | 7 villages, about 113,900 people |
| Variant: 3 town centres as destinations (Shorkot, Athara Hazari, Garh Maharaja; `regions/punjab_trimmu_2025_hubs.yaml`) | the same 2 villages | the same 7 |

- **Which villages.** Bela Surbana and Basti Moharram Sial, near the Chenab–Jhelum confluence. Both were isolated between 29 August and 1 September and reconnected on 13 September.
- **Destinations do not matter.** Using town centres instead of the 3 shelter candidates leaves the result unchanged.
- **Threshold matters, unlike in Sunamganj.** The count changes from 2 to 7 villages between the 20% and 10% thresholds.
- **Thin OSM data.** OSM has only 805 km of road, 26 villages and **3 shelter candidates** in 1,014 km². For comparison, Sunamganj has 4,988 km of road and 50 candidates. The village result is therefore weaker than Sunamganj's, and the town hubs are assumptions, not relief camps.

## 4. News report: a miss that the satellites share

Dawn, 30 August 2025: "Another two breaches were created on a road which leads from Tehsil Chowk of Shorkot to Garh Maharaja."

- **SafeWindow** finds the Shorkot–Garh Maharaja route **open on every date at every threshold**. The direct road is Garh Mahraja Road, 17.9 km in 27 segments. At most 5% of any segment's check-points were flooded.
- **Copernicus EMS agrees.** On each of its five maps, at most 0.97 km of the 17.9 km road lies in flood.
- The breaches were cut deliberately to release water. They are narrow and were not caused by flooding of the road, so **no flood-extent map, ours or EMS's, can see them.** This is a limit of the approach, not a disagreement between sensors.

## 5. What this test fixed in the code (all regions benefit)

1. **Earth Engine export bug.** In Pakistan, `flooded.unmask(255)` exported as all zeros, although Earth Engine computed about 20% flood. The class and its mask now export separately and are combined locally (`02a_sentinel1_gee.py`, `combine_with_swath`).
   - Re-exported with the new code, all 19 Sunamganj 2022 maps and all 24 Sunamganj 2024 maps are pixel-identical to the previous ones (`data/experiments/rerun_v3_2022`, `data/experiments/rerun_v3_2024`).
   - Without this fix, any new region could have shown silent "no flood" maps.
2. **Study area from any polygon** (`area.boundary_file`). This is needed where floods are mapped by AOI rather than by admin units.
3. **The UTM-zone warning worked.** The area straddles 72°E, so the projection was set by hand (EPSG:32643).
4. **Overpass retries.** OSM downloads now wait out 429/502/503/504 from an overloaded server instead of failing (`03_osm_roads_places.py`, `03c_bridges.py`).
5. **News routes between any two places** (`route: points` in the region file).
6. **Benchmark options.** EMS products in several folders are supported (`dir`), and "Not Analysed" footprints are excluded (`exclude_where`).

## 6. Honest summary

The same unchanged pipeline ran end to end in a second country, on a different river system, under a different projection.

- **Independent radar agreement is moderate:** IoU 0.53 one day apart.
- **Same-day agreement with Copernicus EMS on the same Sentinel-1 image:** IoU 0.68.
- **Weaker than in Sunamganj.** The flood changed fast, and SafeWindow probably counts irrigated paddies as flood.
- **Village results:** limited by thin OSM data, but unchanged when the destinations change.
- **The one dated road report** describes man-made breaches that no satellite map can see.

## 7. Next

- **NASA OPERA DSWx-S1** has the same dates here (Phase 4.4); compare it with both SafeWindow and EMS.
- **Rice-paddy hypothesis:** test it with a crop or water-seasonality layer (e.g. JRC Global Surface Water seasonality), decided before looking at the benchmark.
- **Better destinations:** a local list of relief camps (PDMA Punjab) would replace the town-hub assumption.
