"""Tests for the flood-extent benchmark scoring."""

import math

import numpy as np

from safewindow import config
from scripts.build_benchmark import confusion, scores

F, D, U = config.FLOODED, config.DRY, config.UNKNOWN


def test_confusion_counts_only_masked_pixels():
    pred = np.array([[F, F, D, D, U]], dtype="uint8")
    ref = np.array([[F, D, F, D, F]], dtype="uint8")
    mask = (pred != U) & (ref != U)

    assert confusion(pred, ref, mask) == (1, 1, 1, 1)


def test_scores_match_hand_computed_values():
    s = scores(tp=8, fp=2, fn=2, tn=8)

    assert math.isclose(s["iou"], 8 / 12)
    assert math.isclose(s["precision"], 0.8)
    assert math.isclose(s["recall"], 0.8)
    assert math.isclose(s["f1"], 0.8)
    assert math.isclose(s["accuracy"], 0.8)


def test_scores_are_nan_without_flood_in_either_map():
    s = scores(tp=0, fp=0, fn=0, tn=10)

    assert math.isnan(s["iou"]) and math.isnan(s["precision"]) and math.isnan(s["recall"])
    assert s["accuracy"] == 1.0
