"""Step 2 / Source A - Sentinel-1 radar flood maps in Google Earth Engine.

Method (after the UN-SPIDER Recommended Practice for Sentinel-1 flood mapping):
  1. Sentinel-1 GRD, IW mode, VV polarisation, over the study area.
  2. Dry-season reference: median of the region's dates.dry_reference (Feb-Mar
     2022 for sunamganj_2022) from the same relative orbit.
  3. Light speckle filter (30 m focal median).
  4. Flooded = VV below an Otsu threshold (very dark) AND at least 3 dB darker
     than the dry reference (new water, so permanent rivers under bridges are
     not counted as cutting roads). If Otsu gives no plausible threshold
     (outside -26..-12 dB, or too few pixels), the open water is not dark that
     day (typically wind-roughened haor water near -15 dB) and no fixed
     threshold can separate it: the whole map is set to UNKNOWN instead.
     (Until 24 Oct 2026 a fixed -18 dB was used; it caught only a small tail of
     the water. See docs/phase3a_report.md, section 5.)
  5. Steep slopes (> 5 deg, radar shadow) are set to dry. Areas without
     coverage on that date stay UNKNOWN.

    python pipeline/02a_sentinel1_gee.py --list          # list available dates first
    python pipeline/02a_sentinel1_gee.py                 # map every date
    python pipeline/02a_sentinel1_gee.py --dates 2022-06-17 2022-06-29

Needs: `earthengine authenticate` and EE_PROJECT (see safewindow/gee.py).
Saves an Otsu histogram PNG per date in data/processed/flood/otsu/ as proof.
"""
import argparse

import numpy as np
import pandas as pd

from safewindow import config, gee
from safewindow.flood import Grid, read_onto_grid, register_flood_map

DIFF_DB = -3.0          # must be this much darker than the dry season
SLOPE_MAX_DEG = 5
OTSU_PLAUSIBLE_DB = (-26.0, -12.0)   # outside this the histogram has no dark-water mode
MIN_HISTOGRAM_PIXELS = 1000


def otsu(counts: np.ndarray, centers: np.ndarray) -> float:
    """Threshold that maximises between-class variance of a histogram."""
    total = counts.sum()
    w0 = np.cumsum(counts)
    w1 = total - w0
    m0 = np.cumsum(counts * centers)
    mean0 = np.divide(m0, w0, out=np.zeros_like(m0), where=w0 > 0)
    mean1 = np.divide(m0[-1] - m0, w1, out=np.zeros_like(m0), where=w1 > 0)
    between = w0 * w1 * (mean0 - mean1) ** 2
    return float(centers[np.argmax(between)])


def choose_threshold(counts: np.ndarray | None, centers: np.ndarray | None) -> tuple[float | None, str]:
    """Otsu threshold and a status: 'otsu' when usable, otherwise 'otsu_failed'
    (implausible threshold) or 'too_few_pixels'. Only 'otsu' maps are classified."""
    if counts is None or counts.sum() <= MIN_HISTOGRAM_PIXELS:
        return None, "too_few_pixels"
    t = otsu(counts, centers)
    lo, hi = OTSU_PLAUSIBLE_DB
    return t, ("otsu" if lo <= t <= hi else "otsu_failed")


def save_histogram(counts, centers, threshold, day, out, usable=True):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.bar(centers, counts, width=centers[1] - centers[0], color="#4a7db3")
    label = f"Otsu threshold {threshold:.1f} dB" + ("" if usable else " (implausible: map set unknown)")
    ax.axvline(threshold, color="#c0392b", lw=2, ls="-" if usable else "--", label=label)
    ax.set(xlabel="Sentinel-1 VV backscatter (dB)", ylabel="pixels", title=f"Sentinel-1 VV histogram, {day}")
    ax.legend()
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120)
    plt.close(fig)


def collection(ee, aoi):
    return (ee.ImageCollection("COPERNICUS/S1_GRD")
            .filterBounds(aoi)
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
            .select("VV"))


def list_dates(ee, aoi, start: str, end: str) -> pd.DataFrame:
    col = collection(ee, aoi).filterDate(start, end)
    info = col.reduceColumns(ee.Reducer.toList(3), ["system:time_start", "relativeOrbitNumber_start",
                                                     "orbitProperties_pass"]).get("list").getInfo()
    df = pd.DataFrame(info, columns=["t", "relative_orbit", "pass"])
    df["date"] = pd.to_datetime(df["t"], unit="ms").dt.strftime("%Y-%m-%d")
    return (df.groupby("date").agg(relative_orbit=("relative_orbit", "first"), passes=("pass", "first"),
                                   scenes=("t", "size")).reset_index())


def flood_map(ee, aoi, day: str, rel_orbit: int, hist_out, dry_start: str, dry_end: str, slope_mask: bool = True):
    s1 = collection(ee, aoi)
    start = ee.Date(day)
    flood_img = s1.filterDate(start, start.advance(1, "day")).mosaic().focal_median(30, "circle", "meters")

    dry_col = s1.filterDate(dry_start, dry_end)
    same_orbit = dry_col.filter(ee.Filter.eq("relativeOrbitNumber_start", int(rel_orbit)))
    dry = ee.Image(ee.Algorithms.If(same_orbit.size().gt(0), same_orbit.median(), dry_col.median()))
    dry = dry.focal_median(30, "circle", "meters")

    hist = flood_img.reduceRegion(ee.Reducer.histogram(maxBuckets=200, minBucketWidth=0.25),
                                  aoi, scale=60, bestEffort=True).get("VV").getInfo()
    counts = np.array(hist["histogram"], float) if hist else None
    centers = np.array(hist["bucketMeans"], float) if hist else None
    t, status = choose_threshold(counts, centers)
    if t is not None:
        save_histogram(counts, centers, t, day, hist_out, usable=status == "otsu")
    if status != "otsu":
        print(f"  {status} (Otsu {'n/a' if t is None else f'{t:.1f} dB'}): water not separable, map set unknown")
        return None, t, status

    flooded = flood_img.lt(t).And(flood_img.subtract(dry).lt(DIFF_DB))
    if slope_mask:   # off only for the NASADEM ablation test (docs/phase4_report.md, 4.1)
        slope = ee.Terrain.slope(ee.Image("NASA/NASADEM_HGT/001").select("elevation"))
        flooded = flooded.And(slope.lte(SLOPE_MAX_DEG))
    # Where the classification is masked (outside the radar swath, or no dry
    # reference there) the map is UNKNOWN. The mask is exported as a second image
    # and applied locally (see combine_with_swath): in Pakistan (EPSG:32643)
    # `flooded.unmask(255)` exported as all zeros, although both the class and
    # its mask exported correctly on their own.
    # 2 = classified, 1 = masked; the export's clip to the study area writes 0
    # beyond the study area, as the single-image export always did.
    swath = flooded.mask().gt(0).add(1).toByte()
    return (flooded.toByte(), swath), t, status


def combine_with_swath(cls: np.ndarray, swath: np.ndarray) -> np.ndarray:
    """UNKNOWN where the radar did not see (swath == 1), the flood class elsewhere."""
    return np.where(swath == 1, config.UNKNOWN, cls).astype("uint8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="only list available image dates")
    ap.add_argument("--dates", nargs="*", help="only these dates (YYYY-MM-DD)")
    ap.add_argument("--start", default=config.FLOOD_START.isoformat(), help="first date to inspect")
    ap.add_argument("--end", default=config.FLOOD_END.isoformat(), help="last date to inspect")
    ap.add_argument("--dry-start", default=config.DRY_REF_START, help="dry reference start date")
    ap.add_argument("--dry-end", default=config.DRY_REF_END, help="dry reference end date")
    ap.add_argument("--no-slope-mask", action="store_true",
                    help="ablation test only: skip the NASADEM slope mask (write to a separate data folder)")
    args = ap.parse_args()

    paths = config.get_paths()
    if args.no_slope_mask and (paths.data / "submission_evidence.json").exists():
        raise SystemExit(f"{paths.data} holds published results; run the ablation in another SAFEWINDOW_DATA_DIR")
    ee = gee.init()
    paths = paths.ensure()
    grid = Grid.load(paths.grid)
    aoi = gee.study_area_geometry(paths)

    dates = list_dates(ee, aoi, args.start, args.end)
    print(dates.to_string(index=False))
    if args.list:
        return
    if args.dates:
        dates = dates[dates["date"].isin(args.dates)]

    log = []
    for day, orbit in dates[["date", "relative_orbit"]].itertuples(index=False):
        print(f"{day}: orbit {orbit}")
        img, t, status = flood_map(ee, aoi, day, orbit,
                                   paths.flood_dir / "otsu" / f"otsu_{day}.png", args.dry_start, args.dry_end,
                                   slope_mask=not args.no_slope_mask)
        if img is None:
            arr = np.full((grid.height, grid.width), config.UNKNOWN, dtype="uint8")
        else:
            cls_img, swath_img = img
            cls_tif = gee.download_to_grid(cls_img, grid, paths.raw / "sentinel1" / f"s1_{day}_class.tif",
                                           f"s1_{day}", region=aoi, dtype="uint8", nodata=config.UNKNOWN)
            swath_tif = gee.download_to_grid(swath_img, grid, paths.raw / "sentinel1" / f"s1_{day}_swath.tif",
                                             f"s1swath_{day}", region=aoi, dtype="uint8", nodata=config.UNKNOWN)
            arr = combine_with_swath(read_onto_grid(cls_tif, grid), read_onto_grid(swath_tif, grid))
        otsu_txt = "n/a" if t is None else f"{t:.2f}dB"
        register_flood_map(day, "sentinel1", arr, grid, note=f"otsu={otsu_txt} {status} orbit={orbit}", paths=paths)
        share = (arr == config.FLOODED).mean() * 100
        print(f"  {status}: threshold {otsu_txt}, flooded {share:.1f}% of grid")
        log.append({"date": day, "relative_orbit": orbit, "otsu_db": None if t is None else round(t, 2),
                    "status": status, "flooded_pct": round(share, 2)})
    pd.DataFrame(log).to_csv(paths.flood_dir / "sentinel1_log.csv", index=False)


if __name__ == "__main__":
    main()
