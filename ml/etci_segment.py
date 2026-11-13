"""Train and test a flood segmentation model on real Sentinel-1 data (ETCI 2021).

Input: VV and VH backscatter tiles (256 x 256). Target: the ETCI flood mask.
The split is by whole satellite scene, never by tile, so test tiles come from a scene the
model has not seen. The test scene is a Bangladesh scene; the other two Bangladesh scenes
are in training, so the test measures a new date at a known site, not a new country.
A global Otsu threshold on VV is the baseline the network has to beat.

    python ml/etci_segment.py --max-per-scene 400 --epochs 8
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch import nn

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import TemporalFloodUNet  # noqa: E402  (a small U-Net; input_channels=2 here)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "raw" / "etci2021" / "data" / "train"
VAL = ["nebraska_20171222t002118", "northal_20190419t234652"]
TEST = ["bangladesh_20170712t115615", "northal_20190513t234653"]


def load_scene(name: str, limit: int, rng: np.random.Generator):
    """Up to `limit` tiles of a scene (two thirds flooded when available), as uint8 [N, 2, 256, 256] and masks."""
    tiles = DATA / name / "tiles"
    files = sorted(p.name for p in (tiles / "vv").glob("*_vv.png"))
    rng.shuffle(files)
    want_flood, flood, dry = limit * 2 // 3, [], []
    for f in files:
        if len(flood) >= want_flood and len(dry) >= limit - want_flood:
            break
        y = np.array(Image.open(tiles / "flood_label" / f.replace("_vv.png", ".png")))[..., 0] > 0
        (flood if y.any() else dry).append((f, y))
    chosen = (flood + dry)[:limit] if len(flood) >= want_flood else (flood + dry)[:limit]
    X = np.stack([np.stack([np.array(Image.open(tiles / k / f.replace("_vv.png", f"_{k}.png")))[..., 0]
                            for k in ("vv", "vh")]) for f, _ in chosen])
    Y = np.stack([y for _, y in chosen]).astype(np.uint8)
    return X, Y


def load(names, limit, rng):
    parts = [load_scene(n, limit, rng) for n in names]
    return np.concatenate([p[0] for p in parts]), np.concatenate([p[1] for p in parts])


def otsu(values: np.ndarray) -> int:
    hist = np.bincount(values.ravel(), minlength=256).astype(float)
    p = hist / hist.sum()
    w, mu = np.cumsum(p), np.cumsum(p * np.arange(256))
    between = (mu[-1] * w - mu) ** 2 / np.maximum(w * (1 - w), 1e-12)
    return int(np.argmax(between))


def scores(pred: np.ndarray, truth: np.ndarray) -> dict:
    tp = int(((pred == 1) & (truth == 1)).sum())
    fp = int(((pred == 1) & (truth == 0)).sum())
    fn = int(((pred == 0) & (truth == 1)).sum())
    div = lambda a, b: round(a / b, 4) if b else None
    return {"iou": div(tp, tp + fp + fn), "precision": div(tp, tp + fp), "recall": div(tp, tp + fn),
            "f1": div(2 * tp, 2 * tp + fp + fn), "flood_pixels": tp + fn}


@torch.no_grad()
def predict(net, X, device, batch=32):
    net.eval()
    out = []
    for i in range(0, len(X), batch):
        xb = torch.from_numpy(X[i:i + batch]).float().div(255).to(device)
        out.append(net(xb).argmax(1).cpu().numpy().astype(np.uint8))
    return np.concatenate(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-per-scene", type=int, default=400)
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--base-channels", type=int, default=16)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=str(ROOT / "ml" / "etci_model.pt"))
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    torch.manual_seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    held = set(VAL + TEST)
    train_names = [p.name for p in sorted(DATA.iterdir()) if p.name not in held]
    Xtr, Ytr = load(train_names, args.max_per_scene, rng)
    Xva, Yva = load(VAL, args.max_per_scene, rng)
    Xte, Yte = load(TEST, args.max_per_scene, rng)
    print(f"device {device}; tiles train {len(Xtr)}, val {len(Xva)}, test {len(Xte)}", flush=True)

    flood_share = Ytr.mean()
    weight = torch.tensor([1.0, min(float((1 - flood_share) / max(flood_share, 1e-6)), 20.0)]).to(device)
    net = TemporalFloodUNet(input_channels=2, base_channels=args.base_channels).to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=2e-3, weight_decay=1e-4)
    loss_fn = nn.CrossEntropyLoss(weight=weight)
    best, history = -1.0, []
    for epoch in range(1, args.epochs + 1):
        net.train()
        perm = rng.permutation(len(Xtr))
        total = 0.0
        for i in range(0, len(perm), args.batch_size):
            idx = perm[i:i + args.batch_size]
            xb = torch.from_numpy(Xtr[idx]).float().div(255).to(device)
            yb = torch.from_numpy(Ytr[idx]).long().to(device)
            opt.zero_grad()
            loss = loss_fn(net(xb), yb)
            loss.backward()
            opt.step()
            total += loss.item() * len(idx)
        val = scores(predict(net, Xva, device), Yva)
        history.append({"epoch": epoch, "train_loss": round(total / len(perm), 4), "val_iou": val["iou"]})
        print(history[-1], flush=True)
        if (val["iou"] or 0) > best:
            best = val["iou"] or 0
            torch.save({"state": net.state_dict(), "base_channels": args.base_channels}, args.out)

    ckpt = torch.load(args.out, map_location=device)
    net.load_state_dict(ckpt["state"])
    thr = otsu(Xtr[:, 0])
    report = {"split": {"train_scenes": train_names, "val_scenes": VAL, "test_scenes": TEST},
              "tiles": {"train": len(Xtr), "val": len(Xva), "test": len(Xte)}, "epochs": history,
              "otsu_vv_threshold": thr, "test": {}}
    for label, names in [("all_test", TEST)] + [(n, [n]) for n in TEST]:
        X, Y = load(names, args.max_per_scene, np.random.default_rng(args.seed))
        report["test"][label] = {"unet": scores(predict(net, X, device), Y),
                                 "otsu_baseline": scores((X[:, 0] <= thr).astype(np.uint8), Y)}
    Path(args.out).with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["test"], indent=2))


if __name__ == "__main__":
    main()
