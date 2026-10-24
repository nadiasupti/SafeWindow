# Regions

A region file describes one flood in one place. Everything else (the method, its thresholds, the code) is shared by every region, so a new flood needs a new file here, not code changes.

## Pick a region

```powershell
$env:SAFEWINDOW_REGION="sunamganj_2022"        # a file name in this folder, without .yaml
$env:SAFEWINDOW_REGION="D:\path\to\my_flood.yaml"   # or a path to any region file
$env:SAFEWINDOW_DATA_DIR="data/sunamganj_2022"  # keep each region's outputs in its own folder
```

The default is `sunamganj_2022`, which reproduces the published results in `data/live`.

## Add a new flood

1. Copy `sunamganj_2022.yaml` to `<place>_<year>.yaml` and edit it. Each field is commented in that file.
2. Set the two environment variables above, then run the scripts in `pipeline/` in number order, `01` to `07` (commands in [docs/PROJECT_GUIDE.md](../docs/PROJECT_GUIDE.md)).
3. Build the app data (`pipeline/08_build_app_data.py`) and open the app with the same `SAFEWINDOW_REGION`. The app warns if the data was built for a different region.

## Fields

| Field | Meaning |
|---|---|
| `id`, `name` | Short id (used in outputs) and a readable name |
| `area.admin_names` | Admin units fetched from OpenStreetMap, e.g. upazilas or districts |
| `area.admin_unit`, `area.parent`, `area.parent_unit`, `area.country` | Words used in the OSM boundary search, e.g. "Chhatak Upazila, Sunamganj District, Bangladesh" |
| `area.iso3` | Country code for WorldPop (BGD, PAK, BRA ...) |
| `area.bbox` | lon/lat `[west, south, east, north]`; needed for `crs: auto` |
| `crs` | Metric projection, e.g. `"EPSG:32646"`, or `auto` for the UTM zone of the bbox centre (warns when the area spans two zones or is very wide) |
| `dates.flood` | Radar dates to map |
| `dates.dry_reference` | A dry-season window of the same year: the "normal" radar picture |
| `dates.app` | Date range shown in the app (defaults to `dates.flood`) |
| `rain_boxes`, `rain_labels` | Rainfall areas for NASA GPM IMERG (local and upstream) and their display names per language |
| `settlements` | `osm` (OSM village points) or `open_buildings` (clusters of Google Open Buildings: **candidate settlements, not official villages**) |
| `shelters_csv` | Optional local shelter list (columns `name, lat, lon`, optional `type, capacity, verified_by`), relative to the region file. Replaces the OSM shelter candidates |
| `supply_days` | Household supply assumption: default, min, max |
| `languages` | App languages; each needs `locales/<code>.json` |
| `agencies` | Official warning agencies the app tells people to follow |
| `references` | Benchmark sources, for the record |

## Add a language

Copy `locales/en.json` to `locales/<code>.json` and translate the values. Keep the `{...}` placeholders. Set `digits` (ten characters for 0 to 9) and `months` (twelve names) if the language uses its own, and `name_column` if villages have a name column in that language. Then add the code to the region's `languages`. `tests/test_app.py` checks that every locale has the same keys as English.
