# Phase 1b: checking the data for Sunamganj 2024

Date: 24 October 2026. No pipeline code was changed.
Raw results are in `data/experiments/phase1b/` and `data/sources/unosat_2024/`.

## Decision

**Sunamganj, June 2024 can go ahead.** Three reasons:
- There are enough Sentinel-1 images.
- Independent UNOSAT maps from three different sensors fall over our area.
- A dated news report says the Chhatak–Dowarabazar road went under water.

The biggest weakness: together, the independent maps cover only ~15% of our area, and Dowarabazar is barely covered.

---

## 1. Sentinel-1 coverage

Method: computed from scene boundaries (footprints). No images were downloaded.

**Check of the method:** run on 2022, the same script returns exactly 19 dates: 9 cover the whole area and 10 cover part of it. This matches the published results exactly. (`data/experiments/phase1b/s1_coverage_2022.csv`)

| Period | Dates | Whole area covered | Partial |
|---|---|---|---|
| May–July 2022 (published) | 19 | 9 | 10 (16–33% of the area) |
| **May–July 2024** | **24** | **12** | 12 (17–32% of the area) |
| February–March 2024 (dry reference) | 20 | 10 | 10 |

- The same four orbits (41, 77, 114, 150) are present in both 2022 and 2024. So the rule that the dry reference comes "from the same orbit" also works for 2024.
- The partial orbits (114, 150) do not cover Chhatak, and cover only ~9% of Dowarabazar.
- Orbit 77 has no images after 19 June. At the end of June, the only date that covers the whole area is 29 June.

Full lists: `data/experiments/phase1b/s1_coverage_2024.csv`, `data/experiments/phase1b/s1_coverage_2024_dry.csv`.

## 2. UNOSAT `FL20240502BGD` layers and our area

Sources: HDX dataset [`e97de1a2`](https://data.humdata.org/dataset/e97de1a2-2e2d-4371-9d38-f5fede3e79a0) (Sunamganj Sadar), [`cb5f8a67`](https://data.humdata.org/dataset/cb5f8a67-098b-4eb9-8368-1929be47c827) (Chhatak), [`7c143cf3`](https://geo.btaa.org/catalog/7c143cf3-a1cd-4676-9f0e-b0667ecd597b) (Sylhet Division). The shapefiles are in `data/sources/unosat_2024/`.

> Two notes on the archives:
> - The Sadar and Chhatak archives look like separate products, but they contain the same layers.
> - The Chhatak archive also contains a **SAOCOM** (L-band radar) layer.

| Layer (shapefile) | Sensor (from attributes) | Date | Falls in our area | Flooded inside | Nearest Sentinel-1 | Type of check |
|---|---|---|---|---|---|---|
| `PHR_20240626_*_SunamganjSadar` | Pleiades (PHR), optical, very high resolution; has a cloud layer (1.2 km² inside the area) | 26 June 2024, 11:01 | Sadar 121.5 km² (24% of the upazila) + Dowarabazar 20.0 km² (5.7%) | 95.0 km² | **24 June** (covers 97.4% of this area, 2 days earlier); 29 June (100%, 3 days later) | **Independent, different sensor.** But it is optical, so it misses water under trees, and there is a 2–3 day gap |
| `SAOCOM_20240626_*_Sylhet` | SAOCOM, L-band SAR | 26 June 2024 | Chhatak only, 25.3 km² (6.2%) | 13.8 km² | 29 June (3 days later); 19 June (7 days earlier) | **Independent radar** (different band). Larger date gap |
| `SAOCOM_20240626_PotentiallyAffectedRoad_Sylhet` | SAOCOM | 26 June 2024 | **23.5 km** of 327.6 km in total fall in our area | – | 29 June | **A road-level comparison is possible** |
| `GLOBAL_20240626_*_Sunamganj` | "GLOBAL Satellite" (no sensor named) | 26 June 2024, 05:58 | Chhatak 29.9 km² (7.3%) + Dowarabazar 2.1 km² | 15.7 km² | 29 June; 19 June | Sensor unknown, so no tier can be assigned. Report it separately |
| `S1_20240619_20240622_*_Sylhet` | Sentinel-1, machine learning, cumulative over 19 and 22 June | 19 + 22 June 2024 | All three upazilas (Sadar 100%, Chhatak 100%, Dowarabazar 99%) | – | 19 June (whole), 22 June (partial) | **Same sensor**, a method comparison only (like tier C in 2022). It is "cumulative" over two days, so our two daily maps must be combined before comparing |

**Area covered by independent references** (Pleiades + SAOCOM + GLOBAL): about 199 km², ~16% of our area. The same-day references in 2022 (tier A) covered only 2.0% and 7.8%. So 2024 has a larger area for independent checks.

**Left out:** the coastal layers (Satkhira, Rampal, Morrelganj, Paikgachha). They are outside our area and belong to Cyclone Remal (May 2024). Maps of Sylhet District (Sylhet Sadar, Bishwanath, Dakshin Surma) were not found in these archives, and they do not fall in our area either.

## 3. 2024 news reports (roads)

| Source | Published | What it says | Usable? |
|---|---|---|---|
| [The Daily Observer: observerbd.com](https://observerbd.com/news.php?id=477288) | 18 June 2024 | "Several sections of major roads such as ... Chhatak-Dowarabazar have been inundated." Many village roads in Chhatak are under water and cut off. | ✅ A specific road and date. A "Chhatak–Dowarabazar" route question can be set up, like the May 2022 check |
| [The Daily Star, via Asia News Network](https://asianews.network/flood-situation-in-sylhet-sunamganj-worsens/) | 19 June 2024 | Most roads in Chhatak, Dowarabazar, Bishwambharpur and Sadar are under water | ⚠️ General description, no specific route |
| [Prothom Alo: "Floods wreak havoc on roads"](https://en.prothomalo.com/bangladesh/local-news/floods-wreak-havoc-on-roads-in-sylhet-sunamganj) | **27 July 2020** | Chhatak and Dowarabazar cut off from Sadar | ❌ From 2020, left out |
| [The Daily Star: "Floods pummel Northeast"](https://www.thedailystar.net/environment/climate-crisis/natural-disaster/news/floods-pummel-northeast-3049831) | Probably June 2022 (the ID is close to 2022 articles) | – | ❌ Left out until the date is confirmed |

**Next step:** search Bangla newspapers (Prothom Alo, Samakal, local Sunamganj papers) for "Sunamganj–Sylhet road" and "Chhatak–Dowarabazar road" in June 2024, and add more dated reports.

## 4. Plan for Phase 3a

1. Sentinel-1 maps: the 24 dates of May–July 2024. Dry reference February–March 2024, same thresholds.
2. Benchmark, with the date gap stated:
   - Pleiades against our 24 June map (the main independent comparison), and also 29 June. The Pleiades cloud area is excluded.
   - SAOCOM against 29 June and 19 June.
   - GLOBAL in a separate table, with the sensor marked as unknown.
   - UNOSAT Sentinel-1 cumulative against our combined 19 + 22 June map (tier C).
3. Roads: SAOCOM's 23.5 km of "potentially affected road" against our cut roads on 29 June (and 19 June).
4. News: the state of the Chhatak–Dowarabazar route on the last radar date before 17 June and the first radar date after 18 June.

## 5. Cautions about date gaps

- All independent references are from 26 June, but the nearest Sentinel-1 dates are 24 and 29 June. The flood can change in that time, so every result must state the date gap.
- UNOSAT calls all its products "preliminary, not field validated".
- Dowarabazar has almost no independent reference (22 km²).
