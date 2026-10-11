# UNOSAT reference data (event FL20220525BGD)

The archive is 337 MB, too large for this repository. Download it from:

https://unosat-maps.web.cern.ch/BD/FL20220525BGD/FL20220525BGD_SHP.zip

SHA-256: `be72838a57c629672ed942c99b5bd7b11f9789a3677a6bd528af261ce3cdc49d`
Licence: CC BY-SA (as listed on HDX). Publisher: UNITAR-UNOSAT.

The benchmark uses these layers from `FL20220525BGD_SHP/` (AnalysisExtent and FloodExtent for each):

- `Chaohu1_20220525_*_Sylhet`: Chaohu-1, 25 May 2022 (tier A)
- `RCM1_20220618_*_Sylhet`: RCM-1, 18 June 2022 (tier A)
- `RCM1_20220619_*_NE`: RCM-1, 19 June 2022, north-east Bangladesh (tier B)
- `S1_20220525_*_NE`: UNOSAT's Sentinel-1 analysis, 25 May 2022 (tier C)

Extract them into a folder, then run:

    python scripts/build_benchmark.py <folder> --archive FL20220525BGD_SHP.zip

The rasterised reference masks are kept in `data/live/benchmark/`, so the
scores can be checked without the download.

A previous copy of the archive in this folder was a truncated download
(about 15 MB, with no zip directory) and could not be opened. It was removed
on 11 October 2026.
