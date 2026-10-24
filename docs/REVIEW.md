# Independent review of SafeWindow

Thank you for reviewing this project. It should take about an hour. You do not need Earth Engine access or any large downloads.

SafeWindow is a research prototype by team DeltaSentinels (Farhan Labib, Nadia Supti). It estimates when villages in Sunamganj, Bangladesh, lost every road route to a flood shelter during the May–July 2022 flood. The full method is in [data/live/science_methods.md](../data/live/science_methods.md).

## What the project claims

1. **Flood maps.** SafeWindow's Sentinel-1 flood maps agree with UNOSAT flood analyses that were made independently:
   - IoU 0.81–0.84 against other radar satellites on the same day, over 2–8% of the area;
   - IoU 0.89 across the whole area against RCM-1 one day later.
2. **Road cuts match two dated news reports:**
   - **June:** the Sunamganj–Sylhet road link is open on 6 June and cut on 16 June, the date The Daily Star reported it cut. This holds at all three cut thresholds tested.
   - **May:** the Chhatak–Dowarabazar link is cut on the first radar view after its reported 19 May cut, at the 10% and 20% thresholds.
3. **Villages.** At the 20% cut threshold, 5 of 16 villages lose every road route to a shelter candidate at some point. The same 5 are isolated at the 10% and 40% thresholds.
4. **2024 unseen test.** With the method unchanged, the same 5 villages are isolated in the 2024 flood. The flood maps agree with independent Pleiades and SAOCOM analyses (IoU 0.69 and 0.74). See `docs/phase3a_report.md`, which also describes the Otsu-failure rule adopted on 24 October 2026.

The project does **not** claim validated village-level isolation dates, verified shelters, or operational use.

## Checks to run

From the repository root, after `pip install -r requirements-pipeline.txt` and `pip install -e .`:

```powershell
python -m pytest -q                                 # 32 tests
python scripts/build_benchmark.py --check           # re-scores all four benchmark references
python scripts/inspect_data.py data/live            # validates the app data package
python scripts/road_reports_check.py                # the news-report road checks, a few minutes
```

`--check` recomputes every benchmark score from the stored reference masks (`data/live/benchmark/`) and the flood maps. It should end with "All published benchmark metrics reproduced."

## What to read

- `data/live/science_methods.md`: method, benchmark design, results and limitations.
- `data/live/model_evaluation.csv`: metrics per reference and per upazila.
- `data/live/results/road_reports_verdict.csv`: the news-report checks, with sources.
- `safewindow/roads.py`, `safewindow/isolation.py`, `safewindow/timeline.py`: the core engine, about 300 lines.

## Questions for the reviewer

1. Is the Sentinel-1 flood method sound for this region and season?
2. Is the benchmark design fair? In particular:
   - the independence tiers;
   - the absence of tuning on the test dates;
   - the 1 km block bootstrap.
3. Are the road-cut rule and the bridge rule reasonable for 20 m radar?
4. Does the two-graph rule (pessimistic and optimistic) handle missing data honestly?
5. Are the limitations stated clearly, and is any claim stronger than the evidence?

## Recording the review

Replace the empty `independent_review` value in `data/live/submission_evidence.json` with:

```json
"independent_review": {
  "name": "",
  "affiliation": "",
  "contact": "",
  "date": "YYYY-MM-DD",
  "decision": "approved / approved with changes / not approved",
  "summary": "Two or three sentences on what you checked and what you found."
}
```

If the decision is "approved" or "approved with changes", also set `"submission_status": "verified"`. Then:

```powershell
python scripts/verify_submission.py data/live          # should now pass
```

The reviewer should be someone outside the team who did not build the project.
