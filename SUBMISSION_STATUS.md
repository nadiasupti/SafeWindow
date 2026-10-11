# SafeWindow Submission Status

## Status

**Real-region results and an independent flood-extent benchmark are complete. An independent scientific review is still missing.**

Updated 11 October 2026, after the Earth Engine export bug was fixed and every flood map was regenerated. Outputs built before that date were invalid.

## Evidence status

| Requirement | Status |
|---|---|
| Working prototype | Complete |
| Real-region flood maps | Complete: 19 Sentinel-1 dates, 16 May to 12 July 2022 |
| Region-specific benchmark | Complete for flood extent: 2 independent UNOSAT references (Chaohu-1 25 May, RCM-1 18 Jun 2022), covering about 8% of the study area |
| Fixed splits | Complete: both reference dates are test-only, nothing is tuned on them, results are also split by upazila |
| Raw benchmark and evaluation tables | Complete: `benchmark.csv`, `model_evaluation.csv` |
| Metrics, confusion matrix, uncertainty | Complete: IoU, precision, recall, F1, accuracy, block-bootstrap 95% CI (`model_evaluation.json`) |
| Error distribution | Per upazila in `model_evaluation.csv` |
| Source manifest | Complete: `source_manifest.json` |
| Methods, assumptions, limitations | Complete: `science_methods.md` |
| Reproducible commands | In `science_methods.md`, section 9 |
| Independent scientific review | **Missing** |
| Verified shelters | **Missing**: the 50 shelters are unverified OSM candidates |
| Village-level validation (field or news reports) | **Missing** |
| Submission deployment package | Blocked by the independent review |

All evidence files are in `data/live/`.

## Evidence gate

```powershell
.venv\Scripts\python.exe scripts\verify_submission.py data/live
```

This currently fails with exactly two messages: no independent review is recorded, and the status is not `verified`. Both clear once a reviewer outside the team has checked `science_methods.md` and the benchmark. Record their name, affiliation, contact, date and summary in `data/live/submission_evidence.json`, then set `submission_status` to `verified`.

The NASA Space Apps site does not require this gate. It is the project's own standard for claiming scientific validity.

## Claims that can be made

- SafeWindow's Sentinel-1 flood maps agree with independent UNOSAT radar analyses at IoU 0.81–0.84, precision 0.93–0.95 and recall 0.84–0.89, on the areas both cover.
- With the 20% cut threshold, 5 of 16 villages lose every road route to a shelter candidate at some point. The same 5 are isolated at the 10% and 40% thresholds.

## Claims that must not be made

- That isolation dates are validated: they are not checked against field reports.
- That the shelters are real flood shelters: they are unverified OSM candidates.
- That SafeWindow is an operational warning system.
- That the synthetic demo is real-world validation.
- That the FloodNet classifier's accuracy is evidence for the isolation results: it is a separate model.
