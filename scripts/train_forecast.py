"""Train the flood early-warning DEMO model on synthetic data and save it to data/forecast/model.json.

    python scripts/train_forecast.py                 # default: 8000 synthetic village-days, seed 42
    python scripts/train_forecast.py --n 20000 --seed 7

The data is invented (see safewindow/forecast.py), so the printed scores describe how well the model learned the invented
rule on a separate invented sample. They say nothing about real floods. The model is saved with
`validated_on_real_data: false`, and forecast alerts from it go only to test phones.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from safewindow import forecast  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, default=8000, help="number of synthetic village-days")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    model, metrics = forecast.train(args.n, args.seed)
    forecast.save(model, metrics)
    print(json.dumps(metrics, indent=2))
    print("weights:", {f: round(w, 3) for f, w in zip(forecast.FEATURES, model.weights)})
    print(f"saved {forecast.MODEL_PATH}")
    print("This model was trained on SYNTHETIC data and is not validated: forecast alerts stay SIMULATION-only.")


if __name__ == "__main__":
    main()
