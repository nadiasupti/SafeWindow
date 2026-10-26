"""Copy only what the web app needs at runtime into one folder, ready to deploy.

    python scripts/make_deploy_bundle.py --out deploy_bundle
    python scripts/make_deploy_bundle.py --out deploy_bundle --floods live sunamganj_2024

The repository holds raw satellite data and results that a server never reads. The bundle keeps the
app, the library, the locales, the region files, each flood's `app/` package, the requirements, the
Streamlit config and a Dockerfile. Run it from the bundle folder with:

    pip install -r requirements.txt
    streamlit run app/streamlit_app.py

or build the Dockerfile. See docs/DEPLOY.md.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKER = ".safewindow_bundle"

DOCKERFILE = """FROM python:3.12-slim
WORKDIR /srv/safewindow
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home app && chown -R app /srv/safewindow
USER app
ENV PYTHONUNBUFFERED=1
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8501/_stcore/health')"
CMD ["streamlit", "run", "app/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
"""


RUN_BAT = """@echo off
rem Starts SafeWindow with no internet needed. First run installs from the wheels folder if it exists.
cd /d "%~dp0"
set SAFEWINDOW_OFFLINE=1
if not exist .venv\\Scripts\\python.exe (
    python -m venv .venv
    if exist wheels (
        .venv\\Scripts\\python.exe -m pip install --no-index --find-links wheels -r requirements.txt
    ) else (
        .venv\\Scripts\\python.exe -m pip install -r requirements.txt
    )
)
start "" http://localhost:8501
.venv\\Scripts\\python.exe -m streamlit run app\\streamlit_app.py
"""

RUN_SH = """#!/bin/sh
# Starts SafeWindow with no internet needed. First run installs from the wheels folder if it exists.
cd "$(dirname "$0")" || exit 1
export SAFEWINDOW_OFFLINE=1
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
    if [ -d wheels ]; then
        .venv/bin/python -m pip install --no-index --find-links wheels -r requirements.txt
    else
        .venv/bin/python -m pip install -r requirements.txt
    fi
fi
.venv/bin/python -m streamlit run app/streamlit_app.py
"""


def size_mb(path: Path) -> float:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6


def build(out: Path, floods: list[str] | None = None, root: Path = ROOT, wheels: bool = False) -> dict:
    """Create the bundle in `out`. Returns the floods included and the total size in MB."""
    available = sorted(p.parent.parent.name for p in (root / "data").glob("*/app/meta.json"))
    chosen = floods or available
    missing = [f for f in chosen if f not in available]
    if missing:
        raise ValueError(f"no built app package for {missing}; available: {available}")
    if not chosen:
        raise ValueError("no built flood packages under data/*/app")

    previous = None
    if out.exists():
        if not (out / MARKER).exists():
            raise FileExistsError(f"{out} exists and is not a SafeWindow bundle; choose another --out")
        previous = out.with_name(out.name + ".previous")
        shutil.rmtree(previous, ignore_errors=True)
        try:
            os.replace(out, previous)      # fails at once, leaving everything as it was, if the folder is in use
        except PermissionError as exc:
            raise FileExistsError(f"{out} is in use (a running app or an open window?). Stop it, then retry.") from exc
    try:
        (out / "app").mkdir(parents=True)
        shutil.copy2(root / "app" / "streamlit_app.py", out / "app" / "streamlit_app.py")
        if (root / "app" / "static").exists():          # Leaflet served locally, so the map needs no CDN
            shutil.copytree(root / "app" / "static", out / "app" / "static")
        shutil.copytree(root / "safewindow", out / "safewindow", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(root / "locales", out / "locales")
        (out / "regions").mkdir()
        for yaml_file in (root / "regions").glob("*.yaml"):
            shutil.copy2(yaml_file, out / "regions" / yaml_file.name)
        for name in chosen:
            shutil.copytree(root / "data" / name / "app", out / "data" / name / "app")
        shutil.copy2(root / "requirements.txt", out / "requirements.txt")
        (out / ".streamlit").mkdir()
        shutil.copy2(root / ".streamlit" / "config.toml", out / ".streamlit" / "config.toml")
        if (root / "LICENSE").exists():
            shutil.copy2(root / "LICENSE", out / "LICENSE")
        (out / "Dockerfile").write_text(DOCKERFILE, encoding="utf-8", newline="\n")
        (out / ".dockerignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8", newline="\n")
        (out / "run_offline.bat").write_text(RUN_BAT, encoding="utf-8", newline="\r\n")
        (out / "run_offline.sh").write_text(RUN_SH, encoding="utf-8", newline="\n")
        if wheels:      # every Python package, so a machine with no internet can install the app
            subprocess.run([sys.executable, "-m", "pip", "download", "-r", str(out / "requirements.txt"),
                            "-d", str(out / "wheels")], check=True)
        (out / MARKER).write_text("made by scripts/make_deploy_bundle.py; safe to delete and rebuild\n", encoding="utf-8")
    except Exception:
        shutil.rmtree(out, ignore_errors=True)
        if previous is not None:
            os.replace(previous, out)
        raise
    if previous is not None:
        shutil.rmtree(previous, ignore_errors=True)
    return {"floods": chosen, "size_mb": round(size_mb(out), 1)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, type=Path, help="folder to create (rebuilt if it is an earlier bundle)")
    ap.add_argument("--floods", nargs="*", help="data folders to include (default: every built package)")
    ap.add_argument("--wheels", action="store_true",
                    help="also download every Python package, for installs with no internet (needs internet now; "
                         "the wheels match this machine's OS and Python version)")
    a = ap.parse_args()
    try:
        info = build(a.out, a.floods, wheels=a.wheels)
    except (FileExistsError, ValueError) as exc:
        sys.exit(f"error: {exc}")
    print(f"Bundle in {a.out}: floods {info['floods']}, {info['size_mb']} MB")


if __name__ == "__main__":
    main()
