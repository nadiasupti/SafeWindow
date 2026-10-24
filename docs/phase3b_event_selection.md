# Phase 3b: choosing a flood in another country

Date: 24 October 2026. Every number below was checked against the actual archives on this date. None of it is assumed from the event's year.

## Selection rules

1. A river flood lasting weeks, not a flash flood.
2. Independent reference maps (UNOSAT or Copernicus EMS) over a small area.
3. Enough Sentinel-1 passes during the flood.
4. Usable OpenStreetMap roads.
5. NASA data (OPERA, NISAR) actually in the archive for that place and time.

## Candidates

| | Pakistan, Punjab, Aug–Sep 2025 | Pakistan, Punjab, Jul 2026 | Brazil, Rio Grande do Sul, May 2024 | Pakistan, Sindh, 2022 |
|---|---|---|---|---|
| Flood type | Riverine (Chenab, Ravi, Sutlej), weeks | Riverine (Chenab, Ravi), about 1 week (22–29 Jul) | Valley floods in hilly terrain (Taquari), days | Riverine and ponding, months |
| Independent references | **Copernicus EMS EMSR838**: ICEYE (30–31 Aug, 1 Sep) and COSMO-SkyMed (31 Aug, 3 Sep) SAR, plus Pleiades Neo in the north. Also UNOSAT Sentinel-1 (27–28 Aug, same sensor) | Not yet checked | **Copernicus EMS EMSR720**: RADARSAT-2, PAZ and COSMO-SkyMed (4–5 May); Pleiades Neo and WorldView (grading) | UNOSAT FL20220808PAK: Sentinel-1 and Sentinel-2 only |
| Sentinel-1 in Earth Engine | Trimmu AOI: 9 dates, 16 Aug–14 Sep, **all 100% coverage**; dry season Apr–May 2025: 15 dates | – | not checked | – |
| **NASA OPERA DSWx-S1** (CMR search) | **Yes**: Trimmu 8 dates, Sharaqpur 10 dates (20 Aug–9 Sep) | Expected (from Sep 2024 onwards) | **No** (0 granules) | No (before Sep 2024) |
| NASA OPERA DSWx-HLS (optical) | Yes, 13 dates at Trimmu (monsoon cloud likely) | – | – | – |
| **NASA NISAR GCOV** (CMR search) | **No**: science products start 1 Oct 2025 | **Yes**: Trimmu 7 dates in July 2026 (7, 9, 12, 19, 21, 24 Jul and more) | No | No |

Also checked: **OPERA DSWx-S1 has 0 granules for Sunamganj in June 2024.** NISAR GCOV covers Sunamganj on 24 dates from 18 June to 27 September 2026, but no June–July 2026 road-flood reports were found for Sunamganj; the 2026 reports there are April–May flash floods.

## Decision

**Phase 3b: Pakistan, Punjab, August–September 2025, Copernicus EMS AOI 5 "Trimmu" (Jhang, at the Chenab–Jhelum confluence; about 1,040 km²).** It is the only candidate that has all of the following:

- independent radar references from two other constellations (ICEYE and COSMO-SkyMed), one to two days from our Sentinel-1 dates;
- full Sentinel-1 coverage on every date;
- NASA OPERA DSWx-S1 for the same days, for Phase 4.4;
- a weeks-long river flood, comparable to the haor floods.

Sharaqpur (AOI 2, Ravi near Lahore, about 610 km², ICEYE on 30–31 Aug) is a second site if time allows.

**For NISAR (Phase 4.5): Pakistan, Punjab, July 2026.** NISAR GCOV exists for the Chenab and Ravi flood of 22–29 July 2026. Independent references for that event still need to be found.

**Not chosen:**
- **Brazil 2024:** good references, but no OPERA, and hilly valley floods that last days fit the method less well.
- **Sindh 2022:** no independent sensor beyond Sentinel-1/2, and no OPERA.

## What Phase 3b needs next

1. **Study area from the EMS AOI polygon.** `01_study_area.py` finds admin units by name. Add a `area.boundary_file` option to the region file, so any polygon (here the EMSR838 AOI 5 extent) can be the study area.
2. **Dry reference.** April–May 2025 (15 Sentinel-1 dates), the pre-monsoon dry season.
3. **References.** Download the EMSR838 AOI05 delineation products (Sentinel-1 28 Aug, ICEYE 30 and 31 Aug, Sentinel-1 1 and 2 Sep) and write `regions/punjab_trimmu_2025_benchmark.yaml`.
4. **News.** Find dated reports of road or village cut-offs around Trimmu and Jhang, late August 2025.
5. **Settlements.** OSM village coverage in rural Punjab must be checked. If it is thin, use candidate settlements (Phase 2.4) and report it.

## Sources

- Copernicus EMS EMSR838 (Flood in Pakistan, 29 Aug 2025): https://mapping.emergency.copernicus.eu/activations/EMSR838
- Copernicus EMS EMSR720 (Rio Grande do Sul, May 2024): https://mapping.emergency.copernicus.eu/activations/EMSR720
- UNOSAT Pakistan 2025 products (HDX via geo.btaa.org): https://geo.btaa.org/catalog/94566d9a-2496-4d26-8359-31b80a6893cc
- NASA CMR granule search (OPERA_L3_DSWX-S1_V1, OPERA_L3_DSWX-HLS_V1, NISAR_L2_GCOV_PROVISIONAL_V1), queried 24 Oct 2026.
- Punjab July 2026 flooding: https://thestar.com.my/aseanplus/aseanplus-news/2026/07/26/ravi-chenab-swell-as-severe-flooding-spreads-across-punjab
