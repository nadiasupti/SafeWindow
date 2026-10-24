# SafeWindow: methods, evaluation and limitations

SafeWindow estimates, for each village, when it loses every road route to a flood shelter during the May–July 2022 flood in Sunamganj, Bangladesh. It then turns that isolation date into an aid deadline. This document covers:

- the method and the data;
- three flood-extent benchmarks;
- two checks against dated news reports;
- the limits of the results.

Dataset identifiers, licences and processing parameters are in `source_manifest.json`.

SafeWindow is a research prototype. It is not an official warning or evacuation system.

## 1. Study area and grid

- **Area:** Sunamganj Sadar, Chhatak and Dowarabazar upazilas, 1,265 km². Boundaries come from OpenStreetMap.
- **Grid:** one 20 m grid in UTM zone 46N (EPSG:32646), 2,473 × 2,081 pixels.
- **Encoding:** every flood map is stored as 0 = dry, 1 = flooded, 255 = unknown.

## 2. Flood maps (Sentinel-1, with a NASADEM slope mask)

Script: `pipeline/02a_sentinel1_gee.py`. The method follows the UN-SPIDER recommended practice for Sentinel-1 flood mapping.

1. **Input:** Sentinel-1 GRD, IW mode, VV polarisation. There are 19 acquisition dates between 16 May and 12 July 2022.
2. **Speckle filter:** a 30 m focal median.
3. **Dry reference:** the median of February–March 2022, from the same relative orbit where available.
4. **Flood rule:** a pixel is flooded when VV is below an Otsu threshold computed from that date's histogram. It must also be at least 3 dB darker than the dry reference, which leaves out permanent rivers and lakes.
   - **When Otsu fails** (it falls outside −26 to −12 dB, or the histogram has too few pixels), the whole map for that date is set to **unknown**.
   - This happens on 4 dates: 18 May, 11 June, 23 June and 5 July, all orbit 150. On those dates the water peak sits near −15 dB instead of about −22 dB, consistent with wind-roughened haor water. No fixed threshold separates it from land.
   - Until 24 October 2026 a fixed −18 dB was used on these dates. It marked almost no water: 2–6% of the area seen on every date, against 11–15% on the neighbouring dates. That created false "connected" observations. See `scripts/otsu_fallback_check.py`.
5. **Slope mask:** pixels on slopes above 5° are set to dry. Slope comes from NASA's NASADEM and removes radar-shadow false floods.
6. **Coverage gaps:** pixels outside the radar swath stay unknown. On 10 of the 19 dates the swath misses part of the area, leaving 42–53% of the grid unknown.

**MODIS.** The NASA MODIS MOD09GA optical proxy (`pipeline/02c_modis.py`) was computed for all dates. It is not used for road cutting, because 87–100% of the area was cloud-masked on every date. That is why the method relies on radar.

**Export bug, fixed on 11 October 2026.** Earlier versions of `safewindow.gee.download_to_grid` wrote the whole study area into every 800 × 800 tile. No export region was set, and the tile transform was flipped. Everything built before the fix was invalid, and all results here come from regenerated maps. `tests/test_gee.py` guards the tile geometry.

## 3. Road cutting

Script: `pipeline/05_cut_roads.py`.

- **Network:** OpenStreetMap roads with `network_type='all'`, so village paths are included. That gives 21,542 junctions and 24,947 segments.
- **Check-points:** every segment is sampled every 20 m, 286,523 check-points in total.
- **Classification:** a segment is **cut** when more than 20% of its check-points are flooded. Otherwise it is **unknown** when more than half are unknown, and **open** in all other cases. The analysis is repeated at 10% and 40% as a sensitivity test.

**Bridges.** Radar sees the river under a bridge, so a bridge over flood water used to look like a flooded road and cut the route. `pipeline/03c_bridges.py` downloads the OSM road ways tagged as bridges: 534 bridges, 18.7 km in total. Low-water crossings are left out, because they are built to go under water.

At the 1,331 check-points on a bridge, a flooded pixel is treated as dry; a pixel with no radar data stays unknown. The approach roads at each end can still be cut. Before this rule, a 536 m bridge on the Sunamganj–Sylhet Highway falsely cut the route toward Sylhet on 6 June.

## 4. Village isolation

Script: `pipeline/06_isolation.py`.

- **Snapping:** villages and shelters are snapped to their nearest road junction.
- **Boat-dependent villages:** a village more than 500 m from any road.
- **Distant shelters:** a shelter more than 1 km from any road is ignored.
- **Shelters used:** 48 OSM shelter candidates (schools, colleges, clinics, hospitals, community centres). Pharmacies are excluded because they are shops, not places people can shelter in.

For each date the road network is solved twice:

| Graph | Roads used | Village status |
|---|---|---|
| Pessimistic | Only roads seen to be open | **Connected** if it reaches a shelter here |
| Optimistic | Every road not seen to be cut | **Isolated** if it cannot reach a shelter even here |

A village in between is **uncertain**. Missing data therefore widens the answer instead of hiding it.

## 5. Timeline and outcome

Script: `pipeline/07_timeline.py`. Satellites pass only every few days, so isolation is reported as a range, never a single day.

- **Isolation range:** from the day after the village was last seen connected to the first date it was seen isolated.
- **Safe exit date:** the last date seen connected. The route to the nearest shelter on that date is saved.
- **Aid deadline:** the earliest possible isolation day plus household supply days. The default is 7 days, adjustable from 2 to 14 in the app. This is an assumption, not a measurement.

Each village gets one outcome:

| Outcome | Meaning |
|---|---|
| `isolated` | Seen isolated on at least one date |
| `never_isolated` | Seen connected on every date |
| `connected_when_seen` | Connected on every date its roads were observed, unknown on the others |
| `uncertain` | Never determined at all |
| `boat_dependent` | More than 500 m from any road |

Villages are ranked by aid deadline, then by catchment population. Population is the WorldPop 2020 total inside each village's Voronoi cell, clipped to the study area, so no person is counted twice.

## 6. Flood-extent benchmark

Script: `scripts/build_benchmark.py`. Outputs: `benchmark.csv`, `benchmark_manifest.json`, `model_evaluation.csv` and `model_evaluation.json`.

### References

Four UNOSAT analyses of event FL20220525BGD, grouped by how independent they are of SafeWindow:

| Tier | Meaning | Reference | Compared with |
|---|---|---|---|
| A | Different satellite, same day | Chaohu-1, 25 May 2022 | SafeWindow, 25 May |
| A | Different satellite, same day | RCM-1, 18 June 2022 | SafeWindow, 18 June |
| B | Different satellite, one day later | RCM-1, 19 June 2022, north-east Bangladesh | SafeWindow, 18 June |
| C | Same Sentinel-1 data, UNOSAT's own method | Sentinel-1, 25 May 2022 | SafeWindow, 25 May |

Notes on the references:
- UNOSAT, not this team, produced every reference, and none was used to build or tune SafeWindow.
- The 19 June product's flood layer and file name say RCM-1, but its analysis-extent layer lists Sentinel-1. That inconsistency is recorded in the manifest.
- UNOSAT publishes flood extent separately from total water extent. Flood extent is used here because SafeWindow also leaves out permanent water.

### Design

- **Splits.** Fixed temporal hold-out: every reference date is test-only. The method has no trained parameters, and its thresholds were fixed before scoring.
- **Strata.** Results are also reported per upazila.
- **Pixels compared.** Only pixels inside the study area, inside UNOSAT's analysed extent, and with a valid SafeWindow class.
- **Uncertainty.** 95% intervals come from a bootstrap over 1 km blocks (500 resamples, fixed seed).

### Results, whole study area

| Tier | Reference | Area compared | IoU (95% CI) | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| A | Chaohu-1, 25 May | 25.1 km² | 0.835 (0.786–0.876) | 0.930 | 0.891 | 0.910 |
| A | RCM-1, 18 Jun | 98.4 km² | 0.808 (0.788–0.829) | 0.953 | 0.842 | 0.894 |
| B | RCM-1, 19 Jun | 1,248.4 km² | 0.889 (0.884–0.895) | 0.928 | 0.956 | 0.941 |
| C | UNOSAT Sentinel-1, 25 May | 1,261.5 km² | 0.895 (0.889–0.900) | 0.978 | 0.913 | 0.944 |

### IoU per upazila

| Upazila | A, RCM-1 18 Jun | B, RCM-1 19 Jun | C, Sentinel-1 25 May |
|---|---|---|---|
| Sunamganj Sadar | not covered | 0.921 | 0.924 |
| Chhatak | 0.779 | 0.873 | 0.859 |
| Dowarabazar | 0.898 | 0.847 | 0.883 |

The Chaohu-1 comparison lies entirely in Dowarabazar.

### Reading the results

- **Agreement is high in every tier.** It is lowest on the small same-day areas and highest across the whole area.
- **Precision is high (0.93–0.98).** When SafeWindow maps flood, the other analyses almost always agree.
- **Same-day recall is lower (0.84–0.89).** SafeWindow misses some water that RCM-1 and Chaohu-1 map. That fits its strict 3 dB change rule and slope mask.

### Limits

- **Same-day coverage.** The tier A references cover only 2.0% and 7.8% of the study area.
- **One-day offset.** The whole-area tier B reference is one day after the SafeWindow map, so the flood may have changed between them.
- **Tier C.** It shares SafeWindow's input data, so it tests the method, not the data.
- **Not ground truth.** UNOSAT marks its products as preliminary and not validated in the field.
- **Extent only.** These benchmarks score flood extent, not road cuts or isolation dates. Section 7 tests road cuts.

## 7. Road checks against dated news reports

Script: `scripts/road_reports_check.py`. Outputs: `results/road_reports_check.csv` and `results/road_reports_verdict.csv`.

Two reports from The Daily Star are turned into network questions the model answers on every satellite date. The same open, cut and unknown rule is used as for villages.

| Report | What the model is asked | Last radar view before | First radar view after (10% / 20% / 40%) |
|---|---|---|---|
| 20 May 2022: "Road communications between Chhatak and Dowarabazar upazilas of Sunamganj were cut yesterday" (19 May) | Is there any road route between the two upazila towns? | none (the radar missed the route on 16 and 18 May) | 23 May: cut / cut / open |
| 18 June 2022: "road communication with Sunamganj has been cut off from other parts of the country since Thursday" (16 June) | Is there any road route between the two ends of the Sunamganj–Sylhet Highway inside the area (south of Sunamganj town to the edge toward Sylhet)? | 6 June: open / open / open | 16 June: cut / cut / cut |

**Reading these checks:**
- **June report:** matched at every threshold. The link is open on the last view before the reported date and cut on the reported date itself.
- **May report:** matched at the 10% and 20% thresholds, but not at 40%.
- **Unconfirmed cuts:** the model also cuts the highway route on 25 May, 4 June and 30 June at 10% and 20%, though not at 40%. Those cuts come from short highway stretches where 23–55% of check-points read as flooded, which is typical of water against a raised road. A 20 m pixel mixes the dry road crest with the water beside it. No report confirms or rules out these cuts.

Two reports are a small sample. They support the method but do not validate every date.

## 8. Isolation results (main threshold 20%)

| Outcome | Villages |
|---|---|
| Isolated at some point | 5 |
| Connected whenever its roads were observed, unknown on the other dates | 9 |
| Boat-dependent | 2 |

- **Who and when.** The five isolated villages have a combined catchment population of about 187,800 (WorldPop 2020).
  - Four were first seen isolated on 23 May; the fifth, Paschim Birgaon, was already isolated on the first observation, 16 May.
  - Dholkotob and Patharia were last seen connected on 16 May.
  - Boromuha and Purba Birgaon were never seen connected, because their roads were unobserved before 23 May.
  - The five were isolated on 10–15 of the 19 dates, and none was seen reconnected.
- **Change on 24 October 2026.** Before the Otsu-failure rule, the 18 May map made four villages look connected, which gave a "19–23 May" isolation range. The 11 June map made them look reconnected. Both came from maps that showed almost no water. The previous results are in `data/archive/live_v1_2026-10-12/`.
- **Sensitivity.** The same five villages are isolated at the 10%, 20% and 40% cut thresholds. The mean shift in first isolation date is 0 days at 10% and 0.4 days at 40%.
- **Effect of the bridge rule.** Excluding water under bridges changes no village outcome.
- **Not field-checked.** The village results have not been checked against field reports of specific villages. `pipeline/09_validate.py` supports that once a hand-collected `validation/news_reports.csv` exists.

## 9. Known limitations

- **Shelters:** 48 unverified OpenStreetMap candidates, not confirmed flood shelters.
- **Villages:** only 16 OSM village and town points exist in the area. OSM roads are incomplete, and some bridges may not be mapped.
- **Raised roads:** 20 m radar pixels can mark a raised road as flooded when water reaches its foot. The 40% threshold in the sensitivity test bounds this effect.
- **Supply days:** an assumption, not a measured value.
- **Partial swaths:** on 10 of the 19 dates the radar misses part of the area. Villages whose roads lie there are reported as `connected_when_seen`, not `never_isolated`.
- **Unclassifiable dates:** on 4 of the 19 dates Otsu finds no dark-water threshold, and the whole map is unknown. VV radar cannot see wind-roughened open water; VH polarisation, which is less sensitive to wind, is a possible improvement.
- **Roads date:** the OSM roads are a snapshot from October 2026, so roads built after 2022 are included.
- **Population:** catchment population, not the number of people living in the village itself.
- **Review:** no independent scientific review of this work has taken place yet.

## 10. Reproduce

```powershell
earthengine authenticate
$env:EE_PROJECT="<your Earth Engine project>"
python pipeline/02a_sentinel1_gee.py                     # 19 Sentinel-1 flood maps, May-Jul 2022
python pipeline/02c_modis.py --ee-process                # MODIS proxy (trend only)
python pipeline/03b_population.py --worldpop-gee
python pipeline/03c_bridges.py                           # OSM road bridges
python pipeline/02e_merge_flood.py --sources sentinel1
python pipeline/05_cut_roads.py
python pipeline/06_isolation.py
python pipeline/07_timeline.py
python scripts/road_reports_check.py                     # news-report road checks
python pipeline/08_build_app_data.py
# benchmark: download the UNOSAT archive (URL in benchmark_manifest.json), extract the layers
# listed in scripts/build_benchmark.py (REFERENCES), then
python scripts/build_benchmark.py <folder with the shapefiles> --archive FL20220525BGD_SHP.zip
python -m pytest -q
```
