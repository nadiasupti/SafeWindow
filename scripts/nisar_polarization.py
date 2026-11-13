"""NASA-ISRO NISAR L-band in both polarizations (HH and HV), compared with each other and with Sentinel-1 C-band.

    python scripts/nisar_polarization.py sunamganj_2026 --dates 2026-06-18 2026-06-20 2026-07-24
    python scripts/nisar_polarization.py punjab_trimmu_2026 --dates 2026-06-18 2026-07-12 2026-07-24

Needs an Earthdata login saved with earthaccess (netrc). For each date it reads only the HHHH and HVHV chunks
over the study area from the NISAR GCOV granule (HDF5 partial reads over HTTPS), averages them onto the
project's 20 m grid and converts to dB. Then, for each polarization separately, water is "below the Otsu
threshold", chosen with exactly the rule used for Sentinel-1 (choose_threshold in pipeline/02a_sentinel1_gee.py),
so nothing is tuned for NISAR or for HV.

Per date it reports:
  - water area by HH and by HV, and how far they agree;
  - agreement of each with SafeWindow's Sentinel-1 map of the nearest date (within --max-gap days);
  - the median HH, HV and HH-HV (dB) in three groups of pixels: water in both radars, water in NISAR HH only,
    and dry in both. This describes what the backscatter looks like; it is not a new classification.

Edge of the frame: within EDGE_KM (4 km) of the frame's no-data edge the signal fades towards the noise floor and
would look like water, so those pixels are set to no data first (the same for every date and polarization).

Writes:
  data/experiments/nisar_pol_<region>/   dB rasters and water maps (large, local only)
  data/<region>/results/nisar/           small files for the app: nisar.json and PNG layers (WGS84)

No independent flood map exists for these dates: this is agreement between radars and polarizations, not
validation against ground truth. Only the NISAR provisional product (NISAR_L2_GCOV_PROVISIONAL_V1) is used.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import date as Date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

GCOV = "NISAR_L2_GCOV_PROVISIONAL_V1"
MARGIN_M = 200
CHANNELS = {"HH": "HHHH", "HV": "HVHV"}
WATER_RGBA = (30, 110, 230, 255)  # the same blue for every water map, as on the app's flood map
MAX_PX = 1200                     # app layers: sharp enough on a phone, small enough to download
EDGE_KM = 4.0                     # near the edge of a NISAR frame the backscatter falls towards the noise floor
                                  # (measured: about -47 dB at the edge, back to normal 4-6 km in), which looks
                                  # like water; that strip is left out of every map and number, for every date
STRETCH = {"HH": (-25.0, 0.0), "HV": (-32.0, -8.0)}     # fixed dB ranges, the same for every date


def read_on_grid(earthaccess, day: str, grid, bbox, attempts: int = 3):
    """{"HH": dB, "HV": dB} of the NISAR granule on `day`, averaged onto the grid, and the granule name."""
    import time
    for attempt in range(1, attempts + 1):
        try:
            return _read_once(earthaccess, day, grid, bbox)
        except (OSError, RuntimeError) as exc:
            if attempt == attempts:
                raise
            print(f"  {day}: read failed ({type(exc).__name__}), retrying in {30 * attempt}s", flush=True)
            time.sleep(30 * attempt)


def _read_once(earthaccess, day, grid, bbox):
    import h5py
    from rasterio.transform import from_origin
    from rasterio.warp import Resampling, reproject, transform_bounds
    res = earthaccess.search_data(short_name=GCOV, bounding_box=bbox, temporal=(day, day))
    if not res:
        raise SystemExit(f"no NISAR GCOV granule on {day}")
    granule = res[0]["umm"]["GranuleUR"]
    url = next(u for u in res[0].data_links() if u.endswith(".h5"))
    out = {}
    with h5py.File(earthaccess.open([url])[0], "r") as h:
        g = h["science/LSAR/GCOV/grids/frequencyA"]
        src_crs = f"EPSG:{int(g['projection'].attrs['epsg_code'])}"
        x, y = g["xCoordinates"][:], g["yCoordinates"][:]
        left, bottom, right, top = transform_bounds(grid.crs, src_crs, *grid.bounds)
        cols = np.where((x >= left - MARGIN_M) & (x <= right + MARGIN_M))[0]
        rows = np.where((y >= bottom - MARGIN_M) & (y <= top + MARGIN_M))[0]
        c0, c1, r0, r1 = cols.min(), cols.max() + 1, rows.min(), rows.max() + 1
        dx, dy = x[1] - x[0], y[1] - y[0]
        src_transform = from_origin(x[c0] - dx / 2, y[r0] - dy / 2, dx, -dy)
        for pol, name in CHANNELS.items():
            if name not in g:
                raise SystemExit(f"{granule} has no {name}")
            power = g[name][r0:r1, c0:c1].astype("float32")
            on_grid = np.full((grid.height, grid.width), np.nan, dtype="float32")
            reproject(power, on_grid, src_transform=src_transform, src_crs=src_crs, src_nodata=np.nan,
                      dst_transform=grid.transform, dst_crs=grid.crs, dst_nodata=np.nan,
                      resampling=Resampling.average)
            with np.errstate(divide="ignore", invalid="ignore"):
                db = 10 * np.log10(on_grid)
            db[~np.isfinite(db)] = np.nan
            out[pol] = db
    print(f"  {day}: {granule}, read {r1 - r0} x {c1 - c0} px of HH and HV", flush=True)
    return out, granule


def water(db, inside, s1, config, hist_png, day, pol):
    """Water by the Sentinel-1 Otsu rule, for one polarization: (map, threshold, status)."""
    vals = db[inside & np.isfinite(db)]
    counts, edges = np.histogram(vals, bins=np.arange(-40, 10.25, 0.25))     # the same bins as nisar_compare.py
    centers = (edges[:-1] + edges[1:]) / 2
    t, status = s1.choose_threshold(counts.astype(float), centers)
    if t is not None:
        s1.save_histogram(counts, centers, t, day, hist_png, usable=status == "otsu", sensor=f"NISAR L-band {pol}")
    out = np.full(db.shape, config.UNKNOWN, dtype="uint8")
    if status == "otsu":
        known = np.isfinite(db)
        out[known] = config.DRY
        out[known & (db < t)] = config.FLOODED
    return out, t, status


def s1_candidates(flood_dir: Path, day: str, max_gap: int) -> list:
    """(gap in days, path, date) of every Sentinel-1 map within max_gap days, nearest first."""
    out = []
    for p in flood_dir.glob("sentinel1_*.tif"):
        d = p.stem.split("_")[1]
        gap = abs((Date(int(d[:4]), int(d[4:6]), int(d[6:])) - Date.fromisoformat(day)).days)
        if gap <= max_gap:
            out.append((gap, p, f"{d[:4]}-{d[4:6]}-{d[6:]}"))
    return sorted(out, key=lambda c: (c[0], c[2]))


def nearest_s1(flood_dir: Path, day: str, max_gap: int):
    c = s1_candidates(flood_dir, day, max_gap)
    return c[0] if c else None


def pick_s1(flood_dir: Path, day: str, max_gap: int, inside, config):
    """The Sentinel-1 map within max_gap days that saw the most of the study area (then the nearest):
    a map that saw only a corner would make the comparison meaningless. Returns (gap, path, date, array) or None."""
    import rasterio
    best = None
    for gap, path, d in s1_candidates(flood_dir, day, max_gap):
        with rasterio.open(path) as src:
            arr = src.read(1)
        seen = int((inside & (arr != config.UNKNOWN)).sum())
        if best is None or seen > best[0]:
            best = (seen, (gap, path, d, arr))
    return best[1] if best else None


def medians(hh, hv, mask):
    sel = mask & np.isfinite(hh) & np.isfinite(hv)
    if sel.sum() < 50:
        return None
    return {"pixels": int(sel.sum()), "hh_db": round(float(np.median(hh[sel])), 1),
            "hv_db": round(float(np.median(hv[sel])), 1), "hh_minus_hv_db": round(float(np.median(hh[sel] - hv[sel])), 1)}


def to_wgs84(arr, grid, config, resampling, fill):
    from rasterio.warp import calculate_default_transform, reproject
    scale = max(1, max(grid.width, grid.height) / MAX_PX)
    w, h = int(grid.width / scale), int(grid.height / scale)
    t, w, h = calculate_default_transform(grid.crs, config.CRS_WGS84, grid.width, grid.height, *grid.bounds,
                                          dst_width=w, dst_height=h)
    dst = np.full((h, w), fill, dtype=arr.dtype)
    reproject(arr, dst, src_transform=grid.transform, src_crs=grid.crs, src_nodata=fill if not isinstance(fill, float) or not np.isnan(fill) else np.nan,
              dst_transform=t, dst_crs=config.CRS_WGS84, dst_nodata=fill, resampling=resampling)
    west, north = t.c, t.f
    return dst, [[north + t.e * h, west], [north, west + t.a * w]]


def save_png(rgba, path):
    """Water maps (few colours): palette PNG. Radar images (many shades): WebP, lossy with transparency."""
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.fromarray(rgba, "RGBA")
    if path.suffix == ".webp":
        img.save(path, "WEBP", quality=72, method=6)
    else:
        # water maps have only a few exact colours: a palette of exactly those, so no colour or transparency shifts
        # (a lossy reduction changed alpha 255 to 254 and other tools that read these maps then missed the water)
        flat = rgba.reshape(-1, 4)
        colours, index = np.unique(flat, axis=0, return_inverse=True)
        if len(colours) > 256:
            img.save(path, optimize=True)
            return
        pal = Image.fromarray(index.reshape(rgba.shape[:2]).astype("uint8"), "P")
        pal.putpalette([int(c) for col in colours for c in col[:3]] + [0] * (3 * (256 - len(colours))))
        pal.info["transparency"] = bytes(int(col[3]) for col in colours)
        pal.save(path, optimize=True, transparency=bytes(int(col[3]) for col in colours))


def grey_png(db, pol, inside, grid, config, path):
    from rasterio.warp import Resampling
    lo, hi = STRETCH[pol]
    v = np.where(inside, db, np.nan).astype("float32")
    v, bounds = to_wgs84(v, grid, config, Resampling.average, np.nan)
    g = np.clip((v - lo) / (hi - lo), 0, 1)
    rgba = np.zeros(v.shape + (4,), dtype="uint8")
    ok = np.isfinite(v)
    rgba[ok, 0] = rgba[ok, 1] = rgba[ok, 2] = (g[ok] * 255).astype("uint8")
    rgba[ok, 3] = 255
    save_png(rgba, path)
    return bounds


def composite_png(hh, hv, inside, grid, config, path):
    """False colour: red = HH, green = HV, blue = HH - HV (each on a fixed dB scale)."""
    from rasterio.warp import Resampling
    a, _ = to_wgs84(np.where(inside, hh, np.nan).astype("float32"), grid, config, Resampling.average, np.nan)
    b, bounds = to_wgs84(np.where(inside, hv, np.nan).astype("float32"), grid, config, Resampling.average, np.nan)
    r = np.clip((a + 25) / 25, 0, 1)
    gr = np.clip((b + 32) / 24, 0, 1)
    bl = np.clip((a - b) / 15, 0, 1)
    ok = np.isfinite(a) & np.isfinite(b)
    rgba = np.zeros(a.shape + (4,), dtype="uint8")
    for i, ch in enumerate((r, gr, bl)):
        rgba[ok, i] = (ch[ok] * 255).astype("uint8")
    rgba[ok, 3] = 255
    save_png(rgba, path)
    return bounds


def water_png(wmap, inside, grid, config, colour, path):
    from rasterio.warp import Resampling
    m = np.where(inside, wmap, config.UNKNOWN).astype("uint8")
    v, bounds = to_wgs84(m, grid, config, Resampling.mode, config.UNKNOWN)
    rgba = np.zeros(v.shape + (4,), dtype="uint8")
    rgba[v == config.FLOODED] = colour
    rgba[v == config.DRY] = (238, 232, 218, 255)          # land: pale, so the water stands out
    rgba[v == config.UNKNOWN] = (140, 140, 140, 60)
    save_png(rgba, path)
    return bounds


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("region", help="region file name, e.g. sunamganj_2026 (data in data/<region>)")
    ap.add_argument("--dates", nargs="+", required=True)
    ap.add_argument("--max-gap", type=int, default=3, help="days between NISAR and the Sentinel-1 map compared")
    args = ap.parse_args()
    os.environ["SAFEWINDOW_REGION"] = args.region
    os.environ["SAFEWINDOW_DATA_DIR"] = str(ROOT / "data" / args.region)

    import earthaccess
    import rasterio

    import build_benchmark as bb
    from safewindow import config
    from safewindow.flood import Grid, write_flood_map
    from safewindow.places import load_study_area
    spec = importlib.util.spec_from_file_location("s1", ROOT / "pipeline" / "02a_sentinel1_gee.py")
    s1 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(s1)

    earthaccess.login(strategy="netrc")
    paths = config.get_paths()
    grid = Grid.load(paths.grid)
    study = load_study_area(paths)
    bbox = tuple(study.to_crs(config.CRS_WGS84).total_bounds)
    inside = bb.study_zones(grid, study.to_crs(grid.crs))["all"]
    work = ROOT / "data" / "experiments" / f"nisar_pol_{args.region}"
    app = ROOT / "data" / args.region / "results" / "nisar"
    (work / "processed").mkdir(parents=True, exist_ok=True)
    km2 = config.GRID_RES_M ** 2 / 1e6

    scenes = []

    # remove only this script's own earlier layers (dated PNG/WebP and nisar.json): other analyses keep their files
    # in the same folder (e.g. village_water.json from scripts/nisar_village_water.py)
    if app.exists():
        for old in list(app.glob("2026*_*.png")) + list(app.glob("2026*_*.webp")) + [app / "nisar.json"]:
            old.unlink(missing_ok=True)
    cached = json.loads((work / "nisar_polarization.json").read_text(encoding="utf-8")) if (work / "nisar_polarization.json").exists() else {"scenes": []}
    granules = {s["date"]: s["granule"] for s in cached["scenes"]}
    profile = dict(driver="GTiff", height=grid.height, width=grid.width, count=1, dtype="float32",
                   crs=grid.crs, transform=grid.transform, nodata=np.nan, compress="deflate", predictor=3)
    for day in args.dates:
        tag = day.replace("-", "")
        files = {pol: work / "processed" / f"nisar_{pol.lower()}_db_{tag}.tif" for pol in ("HH", "HV")}
        if day in granules and all(f.exists() for f in files.values()):
            db = {}
            for pol, f in files.items():
                with rasterio.open(f) as src:
                    db[pol] = src.read(1)
            granule = granules[day]
            print(f"  {day}: HH and HV from the earlier read ({granule})", flush=True)
        else:
            db, granule = read_on_grid(earthaccess, day, grid, bbox)
            # the raw read is kept as it came (edge included), so a rerun starts from the same data
            for pol in ("HH", "HV"):
                with rasterio.open(files[pol], "w", **profile) as dst:
                    dst.write(db[pol], 1)
        maps, layers = {}, {}
        # the frame edge: pixels within EDGE_KM of no data become no data (see EDGE_KM)
        from scipy import ndimage
        valid = np.isfinite(db["HH"]) & np.isfinite(db["HV"])
        near_edge = valid & (ndimage.distance_transform_edt(valid) * config.GRID_RES_M < EDGE_KM * 1000)
        edge_px = near_edge & inside
        for pol in ("HH", "HV"):
            db[pol] = np.where(valid & ~near_edge, db[pol], np.nan).astype("float32")
        for pol in ("HH", "HV"):
            maps[pol] = water(db[pol], inside, s1, config, work / "histograms" / f"nisar_{pol.lower()}_{day}.png", day, pol)
            write_flood_map(maps[pol][0], grid, work / "processed" / f"nisar_{pol.lower()}_water_{tag}.tif")

        bounds = grey_png(db["HH"], "HH", inside, grid, config, app / f"{tag}_hh.webp")
        grey_png(db["HV"], "HV", inside, grid, config, app / f"{tag}_hv.webp")
        composite_png(db["HH"], db["HV"], inside, grid, config, app / f"{tag}_rgb.webp")
        layers = {"hh": f"{tag}_hh.webp", "hv": f"{tag}_hv.webp", "rgb": f"{tag}_rgb.webp"}
        for pol, colour in (("HH", WATER_RGBA), ("HV", WATER_RGBA)):
            if maps[pol][2] == "otsu":
                water_png(maps[pol][0], inside, grid, config, colour, app / f"{tag}_{pol.lower()}_water.png")
                layers[f"{pol.lower()}_water"] = f"{tag}_{pol.lower()}_water.png"

        hh_w, hv_w = maps["HH"][0], maps["HV"][0]
        edge_km2 = round(float(edge_px.sum() * km2), 1)
        from nisar_compare import agreement
        row = {"date": day, "granule": granule,
               "hh": {"threshold_db": None if maps["HH"][1] is None else round(maps["HH"][1], 2), "status": maps["HH"][2],
                      "water_km2": round(float(((hh_w == config.FLOODED) & inside).sum() * km2), 1)},
               "hv": {"threshold_db": None if maps["HV"][1] is None else round(maps["HV"][1], 2), "status": maps["HV"][2],
                      "water_km2": round(float(((hv_w == config.FLOODED) & inside).sum() * km2), 1)},
               "hh_vs_hv": agreement(hh_w, hv_w, inside), "sentinel1": None, "groups": None, "layers": layers,
               "frame_edge_removed_km2": edge_km2}

        near = pick_s1(paths.flood_dir, day, args.max_gap, inside, config)
        if near:
            sw = near[3]
            water_png(sw, inside, grid, config, WATER_RGBA, app / f"{tag}_s1_water.png")
            layers["s1_water"] = f"{tag}_s1_water.png"
            both = inside & (sw == config.FLOODED) & (hh_w == config.FLOODED)
            nisar_only = inside & (sw == config.DRY) & (hh_w == config.FLOODED)
            dry = inside & (sw == config.DRY) & (hh_w == config.DRY)
            row["sentinel1"] = {"date": near[2], "gap_days": near[0],
                                "water_km2": round(float(((sw == config.FLOODED) & inside).sum() * km2), 1),
                                "hh_vs_s1": agreement(hh_w, sw, inside), "hv_vs_s1": agreement(hv_w, sw, inside)}
            row["groups"] = {"water_in_both": medians(db["HH"], db["HV"], both),
                             "water_in_nisar_hh_only": medians(db["HH"], db["HV"], nisar_only),
                             "dry_in_both": medians(db["HH"], db["HV"], dry)}
        scenes.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != "layers"}, indent=1), flush=True)

    out = {"region": args.region, "product": GCOV, "bounds": bounds, "stretch_db": STRETCH, "frame_edge_km": EDGE_KM,
           "method": "Otsu threshold per polarization, the Sentinel-1 rule unchanged; 20 m grid; "
                     f"the outer {EDGE_KM:g} km of each NISAR frame left out",
           "scenes": scenes}
    app.mkdir(parents=True, exist_ok=True)
    (app / "nisar.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    (work / "nisar_polarization.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"saved {app / 'nisar.json'}")


if __name__ == "__main__":
    main()
