"""Learned estimator of the outages a sparse site missed.

A gradient-boosted model, trained on synthetic sites only (outage_gap/synthetic.py), predicts the log of (true count / counted events)
from what the sparse site sees in its own readings: the number of events seen by exactly 1, 2, 3 and 4 or more of its sensors, its
uptime and its sensor count. The model is stored as plain JSON and evaluated here with numpy, so scikit-learn is not needed.
The 80% range comes from the model's errors on the two real dense Accra sites (calibration/draws_clean.csv).
"""
import json
import pathlib
from dataclasses import dataclass, field
from typing import List
import numpy as np

_FILE = pathlib.Path(__file__).with_name("learned_model.json")
_M = json.loads(_FILE.read_text())
MODEL, RANGES = _M["model"], _M["ranges"]
SIZES = sorted(int(k) for k in RANGES)


def _predict_one(x):
    """Sum the trees for one feature vector (sklearn GradientBoostingRegressor, squared error)."""
    total = MODEL["init"]
    for t in MODEL["trees"]:
        i = 0
        while t["left"][i] != -1:
            i = t["left"][i] if x[t["feature"][i]] <= t["threshold"][i] else t["right"][i]
        total += MODEL["learning_rate"] * t["value"][i]
    return total


@dataclass
class LearnedEstimate:
    sensors: int
    counted_events: int
    seen_by: dict
    uptime: float
    estimated_total: float
    estimated_missed: float
    range_80: List[float]
    curve: str
    warnings: List[str] = field(default_factory=list)


def estimate_learned(sensors, seen_by_1, seen_by_2, seen_by_3, seen_by_4plus, uptime):
    """sensors: sensors at the site (3 to 8). seen_by_j: number of events seen by exactly j of the site's own sensors (4plus: 4 or more).
    uptime: share of time the site's sensors reported (0 to 1). Returns a LearnedEstimate."""
    if not SIZES[0] <= sensors <= SIZES[-1]:
        raise ValueError(f"sensors must be between {SIZES[0]} and {SIZES[-1]}: the model was tested only in that range.")
    counts = (seen_by_1, seen_by_2, seen_by_3, seen_by_4plus)
    if any(c < 0 for c in counts):
        raise ValueError("Event counts must be 0 or more.")
    if not 0 <= uptime <= 1:
        raise ValueError("uptime must be between 0 and 1.")
    if sensors < 4 and seen_by_4plus:
        raise ValueError("A site with fewer than 4 sensors cannot have events seen by 4 or more sensors.")
    n1, n2, n3, n4 = counts
    counted = n2 + n3 + n4
    x = [sensors, n1, n2, n3, n4, uptime, n1 * n1 / (2 * n2 + 1)]
    est = max(counted, 1) * float(np.exp(_predict_one(x)))
    est = max(est, counted)
    r = RANGES[str(sensors)]
    lo, hi = max(est * r["mult_lo"], counted), est * r["mult_hi"]
    w = ["Trained on synthetic sites with randomized uptime, outage rate and outage size; checked on two dense Accra sites and not on other places. Not a utility record."]
    if counted < 10:
        w.append("Fewer than 10 counted events: single months are noisy; use a longer period.")
    if uptime < 0.55 or uptime > 0.97:
        w.append("Uptime is outside the range of the synthetic sites used for training (0.55 to 0.97): treat the estimate with care.")
    if n1 + counted > 0 and n1 / (n1 + counted) > 0.8:
        w.append("Most events were seen by one sensor only. That can mean sensor faults, not outages; check the sensors.")
    return LearnedEstimate(sensors, counted, dict(one=n1, two=n2, three=n3, four_or_more=n4), uptime, round(est, 1), round(est - counted, 1),
                           [round(lo, 1), round(hi, 1)], "Learned estimator (synthetic-data-trained)", w)
