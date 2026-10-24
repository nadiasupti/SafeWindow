# Regions

A region file describes one flood in one place. The method, its thresholds and the code are shared by every region, so a new flood needs a new file here, not code changes.

## Region files in this folder

| File | Flood | Data folder |
|---|---|---|
| `sunamganj_2022.yaml` | Sunamganj, Bangladesh, May–July 2022 (the published study, default) | `data/live` |
| `sunamganj_2024.yaml` | Sunamganj, May–July 2024 (unseen-year test) | `data/sunamganj_2024` |
| `sunamganj_2026.yaml` | Sunamganj, June–August 2026 monsoon (NISAR check) | `data/sunamganj_2026` |
| `punjab_trimmu_2025.yaml` | Trimmu, Jhang, Punjab, Pakistan, August–September 2025 (unseen-country test) | `data/punjab_trimmu_2025` |
| `punjab_trimmu_2025_hubs.yaml` | The same flood, with three town centres (`punjab_trimmu_2025_hubs.csv`) as destinations instead of OSM shelter candidates | separate variant folder |
| `punjab_trimmu_2026.yaml` | Trimmu, July 2026 (NISAR check) | `data/punjab_trimmu_2026` |

Supporting files:
- `*_benchmark.yaml` lists the independent reference maps for a flood (see [Benchmark files](#benchmark-files)).
- `punjab_trimmu_2025_aoi.geojson` is the study-area polygon (Copernicus EMS EMSR838 AOI 5).

## Pick a region

```powershell
$env:SAFEWINDOW_REGION="sunamganj_2024"              # a file name in this folder, without .yaml
$env:SAFEWINDOW_REGION="D:\path\to\my_flood.yaml"    # or a path to any region file
$env:SAFEWINDOW_DATA_DIR="data/sunamganj_2024"       # keep each region's outputs in its own folder
```

Without `SAFEWINDOW_REGION`, the region is `sunamganj_2022`, which reproduces the published results in `data/live`. Clear the variables with `Remove-Item Env:SAFEWINDOW_REGION, Env:SAFEWINDOW_DATA_DIR`.

## Add a new flood

1. **Write the file.** Copy `sunamganj_2022.yaml` to `<place>_<year>.yaml` and edit it. Every field is commented in that file and described below.
2. **Point the pipeline at it.** Set `EE_PROJECT` and the two variables above, using a new data folder.
3. **Run the pipeline.** Run steps `01` to `08` in order. The commands are in the [Pipeline](../README.md#pipeline) table of the main README.
4. **Open the app.** Every built package appears in the app's flood selector. The app warns if a package was built for a different region.
5. **Optional checks.**
   - Add dated news reports (`road_reports`) and run `scripts/road_reports_check.py`.
   - Add independent reference maps (`dates.benchmark`) and run `scripts/benchmark_region.py`.

Do not change the method thresholds for a new flood. That keeps every new region an unseen test.

## Fields

| Field | Meaning |
|---|---|
| `id`, `name` | Short id (used in outputs) and a readable name |
| `area.admin_names` | Admin units fetched from OpenStreetMap, e.g. upazilas or districts |
| `area.admin_unit`, `area.parent`, `area.parent_unit`, `area.country` | Words used in the OSM boundary search, e.g. "Chhatak Upazila, Sunamganj District, Bangladesh" or "Tehsil" in Pakistan |
| `area.boundary_file` | Optional. Any polygon file (e.g. a Copernicus EMS area of interest), relative to the region file. It replaces the admin-unit search |
| `area.iso3` | Country code for WorldPop (BGD, PAK, BRA ...) |
| `area.bbox` | lon/lat `[west, south, east, north]`; needed for `crs: auto` |
| `crs` | Metric projection, e.g. `"EPSG:32646"`, or `auto` for the UTM zone of the bbox centre. Set it by hand when the area spans two UTM zones; the code warns in that case |
| `dates.flood` | Radar dates to map |
| `dates.dry_reference` | A dry-season window of the same year: the "normal" radar picture |
| `dates.app` | Date range shown in the app (defaults to `dates.flood`) |
| `dates.benchmark` | Optional benchmark file in this folder, e.g. `sunamganj_2024_benchmark.yaml` |
| `rain_boxes`, `rain_labels` | Rainfall areas for NASA GPM IMERG (local and upstream) and their display names per language |
| `settlements` | `osm` (OSM village points) or `open_buildings` (clusters of Google Open Buildings: **candidate settlements, not official villages**) |
| `shelters_csv` | Optional local shelter list (columns `name, lat, lon`, optional `type, capacity, verified_by`), relative to the region file. Replaces the OSM shelter candidates |
| `supply_days` | Household supply assumption: default, min, max |
| `languages` | App languages; each needs `locales/<code>.json` |
| `agencies` | Official warning agencies the app tells people to follow |
| `road_reports` | Optional dated news reports of cut roads, checked by `scripts/road_reports_check.py` (format below) |
| `references` | Benchmark sources, for the record |

### News reports (`road_reports`)

Each report names a route the model can answer on every radar date. Use `route: points` with `from` and `to` (lon/lat) for a route between any two places. The two named Sunamganj routes are `chhatak_dowarabazar` and `sunamganj_sylhet_highway`.

```yaml
road_reports:
  - id: shorkot_garh_maharaja
    route: points
    from: [72.0764, 30.8349]   # Shorkot
    to: [71.9037, 30.8335]     # Garh Maharaja
    event_date: "2025-08-30"   # when the road was reported cut
    published: "2025-08-30"
    source: "Newspaper, 'headline', date"
    url: "https://..."
    quote: "The sentence that reports the cut."
```

## Benchmark files

A `*_benchmark.yaml` file lists independent flood maps for one flood, for `scripts/benchmark_region.py`. Each reference names:
- its shapefile layers: `flood`, `analysis`, and an optional `exclude` and `exclude_where`;
- its sensor and date;
- an independence `tier`;
- the SafeWindow dates to score it against (`predictions`). A `"D1+D2"` prediction is the union of two maps.

The reference archives are not stored in git. Download them from the `archives` URLs in the file into the folder named by `shapefile_dir` (under `data/sources/`).

## Add a language

1. Copy `locales/en.json` to `locales/<code>.json` and translate the values. Keep the `{...}` placeholders.
2. Set these keys if the language needs them:
   - `digits` (ten characters for 0 to 9) and `months` (twelve names), if it uses its own;
   - `name_column`, if villages have a name column in that language.
3. Add the code to the region's `languages`.

`tests/test_app.py` checks that every locale has the same keys as English.
