# SafeWindow Submission Status

## Status

**The real-region results, the flood-extent benchmark and the news-report road checks are complete. An independent scientific review is still missing.**

Updated 12 October 2026. The Earth Engine export bug was fixed on 11 October and every flood map was regenerated; outputs built before then were invalid. Road cutting now ignores water under mapped bridges.

## Evidence status

| Requirement | Status |
|---|---|
| Working prototype | Complete |
| Real-region flood maps | Complete: 19 Sentinel-1 dates, 16 May to 12 July 2022 |
| Region-specific benchmark | Complete for flood extent: 4 UNOSAT references in 3 independence tiers. Same-day references from other satellites cover 2–8% of the area; whole-area references are next-day or same-satellite. |
| Fixed splits | Complete: every reference date is test-only, nothing is tuned on them, results are also split by upazila |
| Raw benchmark and evaluation tables | Complete: `benchmark.csv`, `model_evaluation.csv` |
| Metrics, confusion matrix, uncertainty | Complete: IoU, precision, recall, F1, accuracy, block-bootstrap 95% CI (`model_evaluation.json`) |
| Error distribution | Per upazila in `model_evaluation.csv` |
| Road-level check against reports | Complete for 2 dated news reports (`results/road_reports_verdict.csv`) |
| Source manifest | Complete: `source_manifest.json` |
| Methods, assumptions, limitations | Complete: `science_methods.md` |
| Reproducible commands | `science_methods.md`, section 10 |
| Independent scientific review | **Missing**. Reviewer guide ready: `REVIEW.md` |
| Verified shelters | **Missing**: the 48 shelters are unverified OSM candidates. Checklist ready: `data/live/shelter_checklist.csv`, applied with `scripts/shelter_checklist.py apply` |
| Village-level validation (field or news reports) | **Missing** |
| Submission deployment package | Blocked by the independent review |

All evidence files are in `data/live/`.

## Evidence gate

```powershell
.venv\Scripts\python.exe scripts\verify_submission.py data/live
```

This currently fails with exactly two messages: no independent review is recorded, and the status is not `verified`. To clear them, a reviewer outside the team follows [REVIEW.md](REVIEW.md). The review is recorded in `data/live/submission_evidence.json`. The gate accepts it only when every field is filled in and the decision approves.

The NASA Space Apps site does not require this gate. It is the project's own standard for claiming scientific validity.

## Claims that can be made

- **Flood maps.** SafeWindow's Sentinel-1 flood maps agree with UNOSAT analyses from other radar satellites:
  - IoU 0.81–0.84 on the same day, over small areas;
  - IoU 0.89 across the whole area, against a map made one day later.
- **News reports.** The road results match two dated reports:
  - The Sunamganj–Sylhet road link is open on 6 June and cut on 16 June at every threshold tested, as reported.
  - The Chhatak–Dowarabazar route is cut on the first radar view after the reported 19 May cut, at the 10% and 20% thresholds.
- **Villages.** At the 20% cut threshold, 5 of 16 villages lose every road route to a shelter candidate at some point. The same 5 are isolated at the 10% and 40% thresholds.

## Claims that must not be made

- That isolation dates for individual villages are validated: no report of a specific village has been checked.
- That the shelters are real flood shelters: they are unverified OSM candidates.
- That every model road cut is confirmed. Some highway cuts on 25 May, 4 June and 30 June appear only at the 10% and 20% thresholds and are unconfirmed.
- That SafeWindow is an operational warning system.
- That the synthetic demo is real-world validation.
- That the FloodNet classifier's accuracy is evidence for the isolation results: it is a separate model.
