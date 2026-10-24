# Phase 3a report: Sunamganj, May–July 2024 (an unseen flood)

Date: 24 October 2026. Region file: `regions/sunamganj_2024.yaml`. Outputs: `data/sunamganj_2024/`.

**Setup.** This is the same three upazilas, the same OSM snapshot (roads, villages, shelters, bridges) and the same method as the 2022 study. **No threshold was changed.** Only the dates differ:

- 24 Sentinel-1 dates, 2 May to 28 July 2024;
- dry reference from February–March 2024;
- NASA GPM IMERG rainfall for May–July 2024.

## 1. Village outcomes: the same five villages, again

At the 20% cut threshold, **the same 5 villages are isolated in 2024 as in 2022**: Paschim Birgaon, Boromuha, Dholkotob, Purba Birgaon and Patharia, with about 187,800 people in their catchments. All 16 villages have the same outcome category in both years. All three cut thresholds (10%, 20%, 40%) isolate the same 5 villages.

| Village | 2022 first seen isolated | 2024 first seen isolated |
|---|---|---|
| Paschim Birgaon | 16 May | 31 May |
| Boromuha | 23 May | 31 May |
| Patharia | 23 May | 31 May |
| Purba Birgaon | 23 May | 14 May |
| Dholkotob | 23 May | 19 June |

These villages are cut off repeatedly, in two different floods. This is the strongest result so far, because the 2024 data played no part in building the method. As before, village dates are not field-checked.

## 2. Flood extent against independent maps (UNOSAT FL20240502BGD)

`scripts/benchmark_region.py` with `regions/sunamganj_2024_benchmark.yaml`. Every reference is from 26 June except UNOSAT's own Sentinel-1 product. Sentinel-1 did not pass on 26 June, so each reference is scored against the nearest SafeWindow dates, with the gap.

| Reference | Sensor | Area (km²) | Our map (gap) | IoU (95% CI) | Precision | Recall |
|---|---|---|---|---|---|---|
| Pleiades, Sunamganj Sadar (cloud excluded) | optical, very high resolution | 140 | 29 Jun (+3 d) | **0.689** (0.658–0.721) | 0.972 | 0.703 |
| | | 137 | 24 Jun (−2 d), old −18 dB map; now unknown | 0.171 (0.147–0.194) ⚠️ | 0.960 | 0.172 |
| SAOCOM, Chhatak | L-band SAR | 25 | 19 Jun (−7 d) | **0.743** (0.706–0.775) | 0.852 | 0.852 |
| | | 25 | 29 Jun (+3 d) | 0.696 (0.644–0.745) | 0.901 | 0.754 |
| "GLOBAL Satellite", Chhatak | not named | 32 | 19 Jun / 29 Jun | 0.581 / 0.536 | 0.756 / 0.845 | 0.715 / 0.594 |
| UNOSAT Sentinel-1, **total water** | same sensor | 1,262 | 19+22 Jun | **0.906** (0.901–0.911) | 0.998 | 0.908 |
| UNOSAT Sentinel-1, **flood (new water only)** | same sensor | 1,262 | 19+22 Jun | 0.210 | 0.219 | 0.835 |

How to read these results:

- **Precision is high against every independent map (0.85–0.97).** Where SafeWindow maps flood, the other sensors agree. Recall is lower, so SafeWindow misses some water, as it did in 2022.
- **The 24 June map fails** (recall 0.17). That date is an Otsu-fallback date; see section 5.
- **UNOSAT's 2024 "FloodExtent" counts only new or increased water** (17% of the compared area). SafeWindow counts all water that is 3 dB darker than the dry season, including seasonal haor water, which also blocks roads. Against UNOSAT's total-water layer for the same images, IoU is 0.91. The two definitions differ; the like-for-like score is 0.91.
- The 2024 independent references are 3–7 days from our maps and cover about 16% of the study area. In 2022, the same-day references covered 2–8%.

## 3. Road cuts against SAOCOM "potentially affected roads"

`scripts/road_reference_check.py`. UNOSAT marks 23.5 km of road in water on the 26 June SAOCOM image, inside the study area.

| Our map | Threshold | Share of UNOSAT's affected road that we cut | Share of our cut road on UNOSAT's affected road |
|---|---|---|---|
| 19 Jun | 10% / 20% / 40% | 48% / 38% / 21% | 56% / 62% / 71% |
| 29 Jun | 10% / 20% / 40% | 49% / 26% / 13% | 64% / 56% / 71% |

The two road definitions differ:

- UNOSAT's "potentially affected" means any part of the road lies in water.
- A SafeWindow segment is "cut" only when more than 20% of its check-points are flooded.

So SafeWindow is stricter. More than half of what it cuts is confirmed by an independent sensor.

## 4. News report

The Daily Observer, 18 June 2024: "Several sections of major roads such as ... Chhatak-Dowarabazar have been inundated." SafeWindow's route between the two upazila towns:

| | Last radar view before | First view on/after 18 June |
|---|---|---|
| Method as published | 17 Jun: open/open/open | 19 Jun: cut/cut/cut |
| With Otsu-fallback dates set to unknown | 7 Jun: cut/cut/cut | 19 Jun: cut/cut/cut |

The cut on 19 June agrees with the report at every threshold. **The "open on 17 June" should not be claimed as a match:** 17 June is an Otsu-fallback date whose map shows almost no water (section 5).

## 5. A method weakness found by this test: Otsu-fallback dates

When the Otsu threshold falls outside −26 to −12 dB, `02a_sentinel1_gee.py` uses a fixed −18 dB. On those dates the water peak of the radar histogram sits near −15 dB instead of about −22 dB. This is consistent with wind-roughened open water: large haors look bright in VV radar on windy days. The fixed −18 dB then catches only a small tail of the water.

`scripts/otsu_fallback_check.py` compares the flooded share inside the ~973 km² seen on every date:

| Date | Flooded (fallback) | Mean of neighbouring dates |
|---|---|---|
| 2022-05-18 | 1.8% | 10.6% |
| 2022-06-11 | 3.5% | 11.7% |
| 2022-06-23 | 2.0% | 14.8% |
| 2022-07-05 | 5.6% | 14.0% |
| 2024-06-17 | 0.4% | 11.0% |
| 2024-06-24 | 7.6% | 14.0% |

The 2022 fallback dates are all orbit 150. In 2024 they occur on several orbits; three of them (2 May, 5 May and 26 May) fall before the flood, when low values are expected.

**Effect on the results.** Variants were built with every fallback date set to unknown (`data/experiments/variant_2022_nofallback`, `data/experiments/variant_2024_nofallback`):

- **Unchanged:** the 5 isolated villages and their population in both years, at every threshold. Also unchanged: both 2022 news-report checks.
- **Changed in 2022:**
  - Boromuha and Purba Birgaon have no safe exit observed: they were already isolated "on or before 23 May" instead of "between 19 and 23 May".
  - Dholkotob's and Patharia's last safe exit moves from 18 May to 16 May.
  - The "reconnected on 11 June" dates disappear. They came from the 11 June fallback map.
  - Dholposhi changes from "never isolated" to "connected when seen".
- **Changed in 2024:**
  - Dholkotob's last safe exit moves from 17 June to 12 June.
  - The "reconnected on 17 June" dates disappear.

These rules were not tuned on any benchmark. The variant only stops trusting a map whose own threshold step failed.

**Adopted on 24 October 2026.** `pipeline/02a_sentinel1_gee.py` now sets an Otsu-failure date's map to unknown.

- **Rebuilt from Earth Engine with the new code.** For both years, every classified map is pixel-identical to before, and every failed date is fully unknown. The rebuilt maps equal the variants above (2022: 15 + 4 dates, 2024: 19 + 5).
- **New `data/live`.** It now holds the new-rule results, and the previous version is kept in `data/archive/live_v1_2026-10-12/`.
- **2024.** `data/sunamganj_2024/` uses the new rule.
- **Tests.** `tests/test_sentinel1.py` covers the rule.

## 6. Limits

- The roads are the October 2026 OSM snapshot for both floods.
- Independent references are 3–7 days from the radar dates.
- Dowarabazar has almost no independent reference.
- The village dates have not been checked against field reports.
- UNOSAT's products are preliminary and not field-validated.
