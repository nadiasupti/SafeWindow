# Phase 1.3: Benchmark audit

Independent re-check of the four UNOSAT references in `data/live`. Every number below was recomputed from the stored rasters without the benchmark script's own scoring code.

## Per reference (whole study area)

| Reference | Tier | Sensor | Reference date | Our map | UNOSAT flood layer | Analysed area in study (km²) | Compared (km²) | Pixels | TP | FP | FN | TN | IoU | Checks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| chaohu1_20220525 | A | Chaohu-1 SAR | 2022-05-25 | 2022-05-25 | `Chaohu1_20220525_FloodExtent_Sylhet` | 25.1 | 25.1 | 62,697 | 36,240 | 2,733 | 4,448 | 19,276 | 0.8346 | OK |
| rcm1_20220618 | A | RCM-1 SAR | 2022-06-18 | 2022-06-18 | `RCM1_20220618_FloodExtent_Sylhet` | 98.4 | 98.4 | 246,035 | 151,624 | 7,473 | 28,551 | 58,387 | 0.808 | OK |
| rcm1_20220619_ne | B | RCM-1 SAR | 2022-06-19 | 2022-06-18 | `RCM1_20220619_FloodExtent_NE` | 1248.4 | 1248.4 | 3,121,106 | 1,949,262 | 152,371 | 90,246 | 929,227 | 0.8893 | OK |
| unosat_s1_20220525_ne | C | Sentinel-1 SAR | 2022-05-25 | 2022-05-25 | `S1_20220525_FloodExtent_NE` | 1261.5 | 1261.5 | 3,153,648 | 1,766,126 | 40,403 | 167,777 | 1,179,342 | 0.8946 | OK |

Checks per reference: reference-raster SHA-256 matches the manifest; prediction SHA-256 matches; the prediction file's date matches `pred_date`; reference and prediction share the same grid; the confusion counts equal `benchmark.csv`; the IoU equals `model_evaluation.csv`.

## Are the references really different?

| Pair | Identical rasters | Shared analysed area, whole grid incl. outside the study area (km²) | Pixel agreement where both analysed |
|---|---|---|---|
| chaohu1_20220525 vs rcm1_20220618 | False | 59.3 | 0.926 |
| chaohu1_20220525 vs rcm1_20220619_ne | False | 86.1 | 0.836 |
| chaohu1_20220525 vs unosat_s1_20220525_ne | False | 86.3 | 0.916 |
| rcm1_20220618 vs rcm1_20220619_ne | False | 280.2 | 0.897 |
| rcm1_20220618 vs unosat_s1_20220525_ne | False | 280.2 | 0.901 |
| rcm1_20220619_ne vs unosat_s1_20220525_ne | False | 1912.7 | 0.88 |

**Problems found:** none

## Notes

- Resolution of every reference is the project grid (20 m) after rasterising UNOSAT's polygons; the native resolution of each UNOSAT product is not recorded in the archive used here.
- `rcm1_20220619_ne`: UNOSAT's analysis-extent layer lists Sentinel-1, while the flood layer and file name say RCM-1; it is compared with our map from the day before (18 June).
- `unosat_s1_20220525_ne` uses the same Sentinel-1 data as SafeWindow, so it tests the method, not the data.
- UNOSAT products are preliminary and not field-validated: this is agreement between satellite analyses, not ground truth.
