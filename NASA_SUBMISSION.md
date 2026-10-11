# SafeWindow: NASA Space Apps 2026 project page draft

Team **DeltaSentinels**, Dhaka Local Event: Farhan Labib and Nadia Supti.

Paste each section into the matching field on the NASA project page. Fill in the bracketed items first: the official challenge name and the video links.

---

## Challenge

[Select the official 2026 challenge on spaceappschallenge.org and paste its exact title here.]

## High-Level Summary

SafeWindow tells each flood-hit village when it will be cut off from safety, and when aid must arrive.

In the haor wetlands of Sunamganj, Bangladesh, floods hurt people by cutting villages off from shelters, clinics and aid. Most tools show where the water is. Few say when a village loses its last road out, or how long its families can last.

**How it works:**
- Sentinel-1 radar flood maps are built with a NASADEM slope mask.
- The maps are laid over the OpenStreetMap road network for three upazilas.
- The network is solved twice for each satellite date: with only the roads seen open, and with every road not seen cut. Cloud and radar gaps therefore widen the answer instead of hiding it.

**What each village gets:**
- an isolation range;
- a last safe exit date with a route to a shelter;
- an aid deadline (isolation plus household supply days, adjustable in the app).

Villages are ranked by urgency.

**Results for the 2022 flood:**
- **Flood maps:** they agree with independent UNOSAT radar analyses (Chaohu-1 and RCM-1) at IoU 0.81–0.84 and precision 0.93–0.95, on the areas both cover.
- **Villages:** 5 of 16 villages lose every road route at some point, with a combined catchment population of about 187,800.

SafeWindow is a research prototype, not an official warning system.

- 240-second video: [YouTube link]
- Code: https://github.com/nadiasupti/SafeWindow

## Project Demo

[30-second YouTube or Vimeo link]

## Final Project

https://github.com/nadiasupti/SafeWindow, under the MIT licence. Read these first:
- `README.md`
- `data/live/science_methods.md`
- `SUBMISSION_STATUS.md`

## Project Details

### The why, the what, the how

**Why.** Responders need a deadline, not a risk map. During the May–July 2022 flood, haor villages were cut off for weeks. Knowing which village loses its last road first, and when its supplies run out, tells a responder where the first boat or truck should go.

**What.** A Python pipeline and a Streamlit app, in English and Bengali.

The app has:
- a date slider that replays the flood, with villages turning red as they are cut off;
- a village panel showing the isolation range, the safe exit route and the aid deadline;
- a responder view that ranks villages by deadline;
- a Bangla SMS-style alert preview.

**How.**
1. **Flood maps.** Sentinel-1 VV backscatter is filtered, then thresholded with Otsu. A pixel counts as flood only if it is at least 3 dB darker than a February–March 2022 dry reference. Slopes over 5° are masked using NASA NASADEM. There are 19 dates from 16 May to 12 July 2022, all on one 20 m grid.
2. **Road cutting.** Every road segment is sampled every 20 m. A segment is cut when more than 20% of its points are flooded. The analysis is repeated at 10% and 40% as a sensitivity test.
3. **Isolation.** A village is connected if it reaches a shelter on roads seen open, isolated if it cannot even when every unknown road is assumed open, and uncertain in between.
4. **Timeline.** Isolation is reported as a range between satellite passes, never a false single day. The aid deadline is the earliest isolation day plus the household supply days.
5. **Benchmark.** Our maps are compared with independent UNOSAT analyses from two other radar sensors on the same dates. Nothing is tuned on them. Uncertainty comes from a 1 km block bootstrap.

**MODIS.** The NASA MODIS optical proxy was tested. Monsoon cloud masked 87–100% of the area on every date, so the method relies on radar.

**Datasets:**
- NASA GPM IMERG V07
- NASA MODIS MOD09GA v6.1
- NASA NASADEM
- ESA Copernicus Sentinel-1 GRD
- UNITAR-UNOSAT FL20220525BGD
- WorldPop 2020
- OpenStreetMap

### Community involvement and benefits

**Who it helps:**
- emergency responders and union parishad officials, who get a ranked list of which villages to reach first, and by which road;
- aid organisations, who get time to pre-position food and water;
- families, who get a plain Bengali message.

**What we tell users:**
- Results come with their uncertainty.
- Shelters are unverified OpenStreetMap candidates.
- Supply days are an assumption.
- Everyone must follow official alerts (BMD, FFWC, DDM).

**Next steps:**
- verify shelters with local partners;
- check isolation dates against field and news reports;
- seek an independent scientific review.

### Tools and technologies

- **Language and analysis:** Python, Google Earth Engine (Python API), osmnx, networkx, geopandas, shapely, rasterio, numpy, pandas.
- **App:** Streamlit, folium and streamlit-folium, altair.
- **Tests:** pytest, 24 automated tests.
- **Separate classifier:** PyTorch, for the FloodNet image classifier, which is not part of the isolation results.

Credit to the authors and maintainers of these open-source projects, and to OpenStreetMap contributors.

## Use of AI

- **AI in the solution.** None in the core method. Flood mapping uses a statistical Otsu threshold and fixed rules. Isolation uses graph shortest paths. A separate FloodNet image classifier (a convolutional neural network trained on the public FloodNet dataset) is kept in `ml/`. It is not used for any SafeWindow result.
- **AI in development.** Claude (Anthropic), through Claude Code, on 10–11 October 2026. The team asked it to:
  - read and review the repository;
  - find why the flood maps were wrong, which led to fixing the Earth Engine tile export in `safewindow/gee.py`;
  - write the independent benchmark script;
  - rerun the pipeline;
  - draft the documentation, this page, the slides and the video script.

  It worked on the repository code and its outputs. Every result was produced by the code in the repository.
- [Add any other AI tools the team used earlier in development.]

## NASA data sources used

| Dataset | What we used it for |
|---|---|
| GPM IMERG V07 Final Run (`NASA/GPM_L3/IMERG_V07`) | Daily rainfall over Sunamganj and the upstream Meghalaya hills, shown in the app |
| NASADEM (`NASA/NASADEM_HGT/001`) | Slope mask that removes radar-shadow false floods from the Sentinel-1 maps |
| MODIS Terra MOD09GA v6.1 (`MODIS/061/MOD09GA`) | Optical flood-water proxy; tested, and found 87–100% cloud-masked in the monsoon |

**Partner and other data:**
- ESA Copernicus Sentinel-1 GRD, the primary flood source;
- UNITAR-UNOSAT FL20220525BGD, an independent benchmark reference;
- WorldPop 2020 population;
- OpenStreetMap roads, villages and shelter candidates.

## References

- UN-SPIDER Recommended Practice: Flood Mapping and Damage Assessment using Sentinel-1 SAR data in Google Earth Engine.
- UNITAR-UNOSAT, event FL20220525BGD, satellite-detected water extent over Sylhet and Sunamganj, 25 May and 18 June 2022 (CC BY-SA, via HDX). https://unosat-maps.web.cern.ch/BD/FL20220525BGD/FL20220525BGD_SHP.zip
- NASA GPM IMERG V07; NASA NASADEM; NASA MODIS MOD09GA v6.1, through Google Earth Engine.
- ESA Copernicus Sentinel-1 GRD, through Google Earth Engine.
- WorldPop (2020), Global High Resolution Population, 100 m (CC BY 4.0).
- OpenStreetMap contributors (ODbL 1.0); Boeing, G. (2017), OSMnx.
- Otsu, N. (1979), A threshold selection method from gray-level histograms, IEEE Trans. SMC.
