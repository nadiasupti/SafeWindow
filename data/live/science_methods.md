# SafeWindow: methods, evaluation and limitations

SafeWindow estimates, for each village, when it loses every road route to a flood shelter during the May–July 2022 flood in Sunamganj, Bangladesh. It then turns that isolation date into an aid deadline. This document describes the method, the data, the independent flood-extent benchmark, and the limits of the results. The datasets, identifiers, licences and processing parameters are in `source_manifest.json`.

SafeWindow is a research prototype. It is not an official warning or evacuation system.

## 1. Study area and grid

- **Area.** Sunamganj Sadar, Chhatak and Dowarabazar upazilas, 1,265 km². Boundaries come from OpenStreetMap.
- **Grid.** One 20 m grid in UTM zone 46N (EPSG:32646), 2,473 × 2,081 pixels.
- **Encoding.** Every flood map is written onto this grid as 0 = dry, 1 = flooded, 255 = unknown.

## 2. Flood maps (Sentinel-1, with a NASADEM slope mask)

Script: `pipeline/02a_sentinel1_gee.py`. The method follows the UN-SPIDER recommended practice for Sentinel-1 flood mapping.

1. **Input.** Sentinel-1 GRD, IW mode, VV polarisation. There are 19 acquisition dates between 16 May and 12 July 2022.
2. **Speckle.** A 30 m focal median filter is applied.
3. **Dry reference.** The median of February–March 2022, from the same relative orbit where one is available.
4. **Flooded pixels.** A pixel is flooded when VV falls below an Otsu threshold computed from that date's histogram. When the histogram is unimodal (Otsu outside −26 to −12 dB), the threshold falls back to −18 dB. The pixel must also be at least 3 dB darker than the dry reference, which excludes permanent rivers and lakes.
5. **Slope mask.** Pixels on slopes steeper than 5° are set to dry. Slope comes from NASA's NASADEM and removes radar-shadow false positives.
6. **Coverage.** Pixels outside the radar swath stay unknown. On alternate dates the swath covers only part of the area, so 42–53% of the grid is unknown on those dates.

**MODIS.** The NASA MODIS MOD09GA optical proxy (`pipeline/02c_modis.py`) was computed for all 19 dates. It was excluded from road cutting because 87–100% of the study area was cloud-masked on every date. Monsoon cloud is the reason a radar method is needed here.

**Export bug fixed on 11 October 2026.** Earlier versions of `safewindow.gee.download_to_grid` wrote the whole study area into every 800 × 800 pixel tile. Two causes combined:
- No export region was set, so Earth Engine stretched the full image footprint over each tile.
- The tile transform was flipped.

Every flood map and every result built before this fix was invalid. All results below come from maps regenerated after the fix. A regression test is in `tests/test_gee.py`.

## 3. Road cutting

Script: `pipeline/05_cut_roads.py`.

- **Network.** OpenStreetMap roads with `network_type='all'`, so village paths are included. That gives 21,542 junctions and 24,947 segments.
- **Check points.** Each segment is sampled every 20 m, giving 286,523 check points.
- **Classification.** A segment is **cut** when more than 20% of its check points are flooded. Otherwise it is **unknown** when more than half are unknown, and **open** in all other cases.
- **Sensitivity.** The analysis is repeated at 10% and 40% cut thresholds.

## 4. Village isolation

Script: `pipeline/06_isolation.py`.

Villages and shelters are snapped to their nearest road junction. A village more than 500 m from any road is **boat-dependent**. A shelter more than 1 km from any road is ignored.

For each date the road network is solved twice:
- **Pessimistic graph:** only roads seen to be open.
- **Optimistic graph:** every road not seen to be cut.

A village is **connected** if it reaches a shelter in the pessimistic graph and **isolated** if it cannot reach one even in the optimistic graph. Anything in between is **uncertain**. Missing data therefore widens the answer instead of hiding it.

## 5. Timeline and aid deadline

Script: `pipeline/07_timeline.py`. Satellites pass only every few days, so isolation is reported as a range, never a single day:
- **Isolation range.** From the day after the last date seen connected to the first date seen isolated.
- **Safe exit date.** The last date seen connected. The route to the nearest shelter on that date is saved.
- **Aid deadline.** The earliest possible isolation day plus household supply days. The default is 7 days, adjustable from 2 to 14 in the app. This is an assumption, not a measurement.

Villages are ranked by aid deadline, then by catchment population. Population is the WorldPop 2020 total inside each village's Voronoi cell, clipped to the study area, so no person is counted twice.

## 6. Independent flood-extent benchmark

Script: `scripts/build_benchmark.py`. Outputs: `benchmark.csv`, `benchmark_manifest.json`, `model_evaluation.csv` and `model_evaluation.json`.

### References

Two UNOSAT flood-extent analyses from event FL20220525BGD:

| Reference | Sensor | Date |
|---|---|---|
| `chaohu1_20220525` | Chaohu-1 SAR | 25 May 2022 |
| `rcm1_20220618` | RCM-1 (RADARSAT Constellation Mission) SAR | 18 June 2022 |

**Why they count as independent:**
- Both sensors differ from Sentinel-1.
- The analyses were produced by UNITAR-UNOSAT, not by this team.
- Neither was used to build or tune SafeWindow's maps.
- Both dates match Sentinel-1 acquisitions exactly.

UNOSAT publishes flood extent separately from total water extent. The flood-extent layer is used here because SafeWindow's 3 dB change rule also leaves out permanent water.

### Design

- **Splits.** Fixed temporal hold-out: both reference dates are test-only. The method has no trained parameters, and the thresholds were fixed before scoring and not tuned on these dates.
- **Geographic strata.** Results are also reported per upazila.
- **Pixels compared.** Only pixels inside the study area, inside UNOSAT's analysed extent, and with a valid SafeWindow class.
- **Uncertainty.** 95% intervals come from a bootstrap over 1 km blocks (500 resamples, fixed seed), because neighbouring pixels are correlated.

### Results (study area, all compared pixels)

| Reference | Area compared | IoU (95% CI) | Precision | Recall | F1 | Accuracy |
|---|---|---|---|---|---|---|
| Chaohu-1, 25 May 2022 | 25.1 km² | 0.835 (0.786–0.876) | 0.930 | 0.891 | 0.910 | 0.886 |
| RCM-1, 18 Jun 2022 | 98.4 km² | 0.808 (0.788–0.829) | 0.953 | 0.842 | 0.894 | 0.854 |

### Per upazila (RCM-1, 18 June)

| Upazila | IoU | Precision | Recall |
|---|---|---|---|
| Chhatak | 0.779 | 0.959 | 0.806 |
| Dowarabazar | 0.898 | 0.937 | 0.956 |

The Chaohu-1 comparison falls entirely in Dowarabazar.

### Reading the results

- **High precision (0.93–0.95).** When SafeWindow says a pixel is flooded, the independent analysis almost always agrees.
- **Lower recall (0.84–0.89).** SafeWindow misses some water that UNOSAT maps. That is consistent with the strict 3 dB change rule and the slope mask. For isolation this is the conservative direction for false alarms, but it can make a road look open when it is not.

### Limits of the benchmark

- **Coverage.** The compared area is a small share of the 1,265 km² study area: about 2% for Chaohu-1 and 8% for RCM-1. Chaohu-1 overlaps only Dowarabazar, and RCM-1 overlaps Chhatak and Dowarabazar. Neither covers Sunamganj Sadar.
- **Not ground truth.** UNOSAT marks both products as preliminary and not validated in the field. This is agreement between two satellite analyses.
- **Flood extent only.** The benchmark scores flood extent. It does not directly test road cutting or village isolation dates.

## 7. Isolation results (main threshold 20%)

| Outcome | Villages |
|---|---|
| Isolated at some point | 5 |
| Uncertain (route only through roads under missing data) | 8 |
| Boat-dependent | 2 |
| Never isolated | 1 |

- **Who is isolated.** The five isolated villages have a combined catchment population of about 187,800 (WorldPop 2020). Four were first seen isolated on 23 May; the fifth was already isolated on the first observation, 16 May.
- **Sensitivity.** The same five villages are isolated at 10%, 20% and 40% cut thresholds. The mean shift in first isolation date is 0 days at 10% and 0.4 days at 40%.

These village results have **not** been checked against field reports. The news-report check in `pipeline/09_validate.py` needs a hand-collected `validation/news_reports.csv`, which does not exist yet.

## 8. Known limitations

- **Shelters.** Shelters are 50 unverified OpenStreetMap candidates (schools, clinics, offices), not confirmed flood shelters.
- **Villages.** Only 16 OSM village and town points exist in the area. OSM roads are incomplete.
- **Supply days.** An assumption, not a measured value.
- **Coverage gaps.** Alternate-date radar swaths leave 42–53% of the area unknown, which is why many villages are uncertain.
- **Population.** Catchment population, not the number of people living in the village itself.
- **No independent review.** No independent scientific review of this work has taken place yet.

## 9. Reproduce

```powershell
earthengine authenticate
$env:EE_PROJECT="<your Earth Engine project>"
python pipeline/02a_sentinel1_gee.py                     # 19 Sentinel-1 flood maps, May-Jul 2022
python pipeline/02c_modis.py --ee-process                # MODIS proxy (trend only)
python pipeline/03b_population.py --worldpop-gee
python pipeline/02e_merge_flood.py --sources sentinel1
python pipeline/05_cut_roads.py
python pipeline/06_isolation.py
python pipeline/07_timeline.py
python pipeline/08_build_app_data.py
# benchmark: download the UNOSAT archive (URL in benchmark_manifest.json), extract the
# Chaohu1_20220525_* and RCM1_20220618_* AnalysisExtent/FloodExtent shapefiles, then
python scripts/build_benchmark.py <folder with the shapefiles> --archive FL20220525BGD_SHP.zip
python -m pytest -q
```
