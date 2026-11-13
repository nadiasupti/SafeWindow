"""Make the mobile app's icons and header logo from the two brand images in pwa/brand/.

    python scripts/make_pwa_icons.py

    pwa/brand/app_icon.png  the app icon: a rounded square on a light background (any size, square)
    pwa/brand/logo.png      the wide logo with the name (transparent background)

Writes, small enough to ship with the app:
    pwa/public/icons/icon-192.png, icon-512.png          home screen (rounded square, transparent corners)
    pwa/public/icons/maskable-192.png, maskable-512.png  Android adaptive icon (full square: corners filled)
    pwa/public/icons/apple-touch-icon.png                iPhone home screen (full square, no transparency)
    pwa/public/icons/favicon-64.png                      browser tab
    pwa/public/brand/logo-header.png                     the logo for the app's top bar

The originals stay in pwa/brand/, outside public/, so they are never deployed. Run again when either image changes.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "pwa" / "brand"
ICONS = ROOT / "pwa" / "public" / "icons"
BRAND_OUT = ROOT / "pwa" / "public" / "brand"
HEADER_HEIGHT = 96          # px: 2x the 48 px the top bar shows, sharp on phone screens
CORNER = 0.22               # rounded-square corner radius, as a share of the side (matches the drawing)


def tile(src: Image.Image) -> Image.Image:
    """The rounded square itself: the drawing without its white background and soft shadow."""
    rgb = src.convert("RGB")
    # pixels clearly darker than the white page belong to the tile
    gray = rgb.convert("L").point(lambda v: 255 if v < 200 else 0)
    box = gray.getbbox()
    if not box:
        raise SystemExit("app_icon.png: no tile found (expected a coloured rounded square on a light background)")
    left, top, right, bottom = box
    side = max(right - left, bottom - top)
    cx, cy = (left + right) // 2, (top + bottom) // 2
    square = rgb.crop((cx - side // 2, cy - side // 2, cx - side // 2 + side, cy - side // 2 + side))
    mask = Image.new("L", square.size, 0)
    inset = max(2, side // 200)                       # cut just inside the edge, so no white rim or shadow is kept
    ImageDraw.Draw(mask).rounded_rectangle([inset, inset, side - 1 - inset, side - 1 - inset],
                                           radius=int(side * CORNER), fill=255)
    out = square.convert("RGBA")
    out.putalpha(mask.filter(ImageFilter.GaussianBlur(1)))
    return out


def edge_colour(t: Image.Image) -> tuple[int, int, int]:
    """The tile's background colour near its edge (left middle), to fill the corners of full-square icons."""
    side = t.width
    return t.convert("RGB").getpixel((int(side * 0.06), side // 2))


def full_square(t: Image.Image, size: int, scale: float = 1.0) -> Image.Image:
    """The tile filling a whole square: no transparent or white corners. A scale below 1 keeps the drawing inside
    Android's safe zone (the middle 80% circle every launcher shape keeps); the space around it is a blurred,
    enlarged copy of the tile itself, so its colours run on with no visible second frame."""
    base = Image.new("RGBA", (size, size), edge_colour(t) + (255,))
    base.alpha_composite(t.resize((size, size), Image.LANCZOS))
    if scale >= 1:
        return base
    import numpy as np
    inner = round(size * scale)
    # the tile without its light rim (outer 5%), shrunk, then its border pixels stretched outward:
    # the colours run on with no seam or second frame
    rim = round(t.width * 0.05)
    core = full_square(t, t.width).convert("RGB").crop((rim, rim, t.width - rim, t.width - rim))
    arr = np.asarray(core.resize((inner, inner), Image.LANCZOS))
    before = (size - inner) // 2
    arr = np.pad(arr, ((before, size - inner - before), (before, size - inner - before), (0, 0)), mode="edge")
    out = Image.fromarray(arr)
    soft = out.filter(ImageFilter.GaussianBlur(size * 0.03))
    keep = Image.new("L", (size, size), 0)
    ImageDraw.Draw(keep).rectangle([before + 2, before + 2, before + inner - 3, before + inner - 3], fill=255)
    out = Image.composite(out, soft, keep.filter(ImageFilter.GaussianBlur(3)))
    return out.convert("RGBA")


def save(img: Image.Image, path: Path, flat: bool = False) -> None:
    """PNG. `flat` artwork (the logo: few colours, no gradient) is reduced to 256 colours, a fraction of the size;
    the icons keep every colour, since their gradient would show bands."""
    if flat:
        img.convert("RGBA").quantize(colors=256, method=Image.Quantize.FASTOCTREE).save(path, optimize=True)
    else:
        img.save(path, optimize=True)


def header_logo(src: Image.Image) -> Image.Image:
    """The wide logo cropped to its drawing and scaled to the top bar's height."""
    logo = src.convert("RGBA")
    alpha = logo.getchannel("A").point(lambda v: 255 if v > 24 else 0)
    box = ImageChops.lighter(alpha, alpha).getbbox()
    logo = logo.crop(box)
    width = round(logo.width * HEADER_HEIGHT / logo.height)
    return logo.resize((width, HEADER_HEIGHT), Image.LANCZOS)


def main() -> None:
    for name in ("app_icon.png", "logo.png"):
        if not (SRC / name).exists():
            raise SystemExit(f"{SRC / name} is missing")
    ICONS.mkdir(parents=True, exist_ok=True)
    BRAND_OUT.mkdir(parents=True, exist_ok=True)
    t = tile(Image.open(SRC / "app_icon.png"))
    for size in (192, 512):
        save(t.resize((size, size), Image.LANCZOS), ICONS / f"icon-{size}.png")
        save(full_square(t, size, scale=0.84), ICONS / f"maskable-{size}.png")
    save(full_square(t, 180).convert("RGB"), ICONS / "apple-touch-icon.png")
    save(t.resize((64, 64), Image.LANCZOS), ICONS / "favicon-64.png")
    save(header_logo(Image.open(SRC / "logo.png")), BRAND_OUT / "logo-header.png", flat=True)
    for p in sorted(list(ICONS.glob("*.png")) + [BRAND_OUT / "logo-header.png"]):
        print(f"  {p.relative_to(ROOT)}  {Image.open(p).size}  {p.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
