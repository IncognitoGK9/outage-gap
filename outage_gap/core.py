"""Core of OutageGap: detection curve, estimate and sensor planning. No web framework needed.

A "calibration" is a dictionary with a detection share and an error range for each sensor count.
The shipped one (calibration.json) was measured on two dense sites in Accra. You can measure your own
with outage_gap.calibrate.calibrate() and pass it as `cal=` to every function here.
"""
import json
import pathlib
from dataclasses import dataclass, field

CAL = json.loads((pathlib.Path(__file__).parent / "calibration.json").read_text())
SIZES = sorted(int(k) for k in CAL["k"])      # sensor counts measured in the shipped curve: 3, 4, 5, 6, 7, 8
LOW_UPTIME = 0.65
UPTIME_GAP = 0.15                             # own-curve warning: site uptime this far from the reference uptime
DEFAULT_NAME = "Accra dense sites 3 and 4 (shipped curve)"


@dataclass
class Estimate:
    sensors: int
    observed_events: int
    detection_share: float
    estimated_total: float
    estimated_missed: float
    range_80: list
    interpolated: bool
    curve: str = DEFAULT_NAME
    warnings: list = field(default_factory=list)


def check_calibration(cal):
    """Raise ValueError with a clear message if a calibration dictionary is not usable."""
    if not isinstance(cal, dict) or not isinstance(cal.get("k"), dict) or not cal["k"]:
        raise ValueError("A calibration must be a dictionary with a non-empty 'k' entry (see GET /curve).")
    for key, p in cal["k"].items():
        try:
            int(key)
        except ValueError:
            raise ValueError(f"Calibration key '{key}' is not a sensor count.")
        for need in ("c", "err_q10", "err_q90"):
            if need not in p:
                raise ValueError(f"Calibration entry for {key} sensors lacks '{need}'.")
        if not 0 < p["c"] <= 1.5:
            raise ValueError(f"Calibration entry for {key} sensors has a detection share outside (0, 1.5].")
    return cal


def sizes_of(cal=None):
    cal = cal or CAL
    return sorted(int(k) for k in cal["k"])


def curve(k: int, cal=None):
    """Detection share and 10th/90th percentile errors for k sensors (linear between measured sizes)."""
    cal = cal or CAL
    sizes = sizes_of(cal)
    if k in sizes:
        p = cal["k"][str(k)]
        return p["c"], p["err_q10"], p["err_q90"], False
    lo = max(x for x in sizes if x < k)
    hi = min(x for x in sizes if x > k)
    w = (k - lo) / (hi - lo)
    a, b = cal["k"][str(lo)], cal["k"][str(hi)]
    f = lambda key: a[key] + w * (b[key] - a[key])
    return f("c"), f("err_q10"), f("err_q90"), True


def estimate(sensors: int, observed_events: int, uptime=None, cal=None) -> Estimate:
    """Estimate the full outage count of a sparse site from the count it saw (events seen by 2+ sensors of its own)."""
    own = cal is not None
    cal = check_calibration(cal) if own else CAL
    sizes = sizes_of(cal)
    if not sizes[0] <= sensors <= sizes[-1]:
        raise ValueError(f"sensors must be between {sizes[0]} and {sizes[-1]}: the curve was measured only in that range.")
    if observed_events < 0:
        raise ValueError("observed_events must be 0 or more.")
    if uptime is not None and not 0 <= uptime <= 1:
        raise ValueError("uptime must be between 0 and 1.")
    c, q10, q90, interp = curve(sensors, cal)
    est = observed_events / c
    lo, hi = est / (1 + q90), est / (1 + q10)
    name = cal.get("source", "your own dense data") if own else DEFAULT_NAME
    if own:
        w = [f"Estimate uses your own curve: {name}."]
        ref_up = cal.get("reference_uptime")
        if uptime is not None and ref_up is not None and abs(uptime - ref_up) > UPTIME_GAP:
            w.append(f"Site uptime {uptime:g} differs from the reference uptime {ref_up:g} by more than {UPTIME_GAP:g}: "
                     "the detection share may not transfer.")
        elif uptime is None and ref_up is not None:
            w.append(f"Uptime not given: the estimate assumes sensor uptime like the reference sites ({ref_up:g}).")
        for x in cal.get("warnings", []):
            w.append(x)
    else:
        w = ["Estimate for Accra-like sites, calibrated on two dense sites in Accra only; not a utility record."]
        if uptime is None:
            w.append("Uptime not given: the estimate assumes sensor uptime like the reference sites.")
        elif uptime < LOW_UPTIME:
            w.append("Low uptime: in simulation, a curve learned at uptime 0.8 underestimated the total by 12% (8 sensors) to 43% (3 sensors) at uptime 0.5.")
    if observed_events < 10:
        w.append("Fewer than 10 observed events: single months are noisy; use a longer period.")
    if interp:
        w.append("Sensor count lies between measured sizes; the curve is interpolated.")
    return Estimate(sensors, observed_events, round(c, 4), round(est, 1), round(est - observed_events, 1),
                    [round(lo, 1), round(hi, 1)], interp, name, w)


def plan(target_share: float, cal=None):
    """How many sensors does a site need so that its own count reaches `target_share` of the reference count?

    Uses the measured sensor counts first, then the larger sizes of the saturation test (share only, no range).
    The shares are relative to the dense reference sites, so they are upper bounds on the real share.
    """
    if not 0 < target_share <= 1:
        raise ValueError("target_share must be above 0 and at most 1.")
    cal = check_calibration(cal) if cal is not None else CAL
    rows = {k: dict(sensors=k, detection_share=cal["k"][str(k)]["c"],
                    missed_per_100=round(100 * (1 - cal["k"][str(k)]["c"]), 1),
                    median_single_month_error=cal["k"][str(k)].get("median_abs_err"), has_range=True)
            for k in sizes_of(cal)}
    for ks, p in cal.get("saturation", {}).items():
        k = int(ks)
        if k not in rows:
            rows[k] = dict(sensors=k, detection_share=p["c"], missed_per_100=round(100 * (1 - p["c"]), 1),
                           median_single_month_error=None, has_range=False)
    table = [rows[k] for k in sorted(rows)]
    hit = next((r["sensors"] for r in table if r["detection_share"] >= target_share), None)
    note = ("Shares are measured against the dense reference sites, so they are upper bounds: the real share is lower. "
            "Sizes without a range were measured in the saturation test only.")
    if hit is None:
        note = f"No tested sensor count reaches a share of {target_share:g}. " + note
    return dict(target_share=target_share, sensors_needed=hit, table=table, note=note)
