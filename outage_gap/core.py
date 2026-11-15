"""Core of OutageGap: detection curve and estimate. No web framework needed."""
import json
import pathlib
from dataclasses import dataclass, field

CAL = json.loads((pathlib.Path(__file__).parent / "calibration.json").read_text())
SIZES = sorted(int(k) for k in CAL["k"])      # measured sensor counts: 3, 4, 5, 6, 7, 8
LOW_UPTIME = 0.65


@dataclass
class Estimate:
    sensors: int
    observed_events: int
    detection_share: float
    estimated_total: float
    estimated_missed: float
    range_80: list
    interpolated: bool
    warnings: list = field(default_factory=list)


def curve(k: int):
    """Detection share and 10th/90th percentile errors for k sensors (linear between measured sizes)."""
    if k in SIZES:
        p = CAL["k"][str(k)]
        return p["c"], p["err_q10"], p["err_q90"], False
    lo = max(x for x in SIZES if x < k)
    hi = min(x for x in SIZES if x > k)
    w = (k - lo) / (hi - lo)
    a, b = CAL["k"][str(lo)], CAL["k"][str(hi)]
    f = lambda key: a[key] + w * (b[key] - a[key])
    return f("c"), f("err_q10"), f("err_q90"), True


def estimate(sensors: int, observed_events: int, uptime=None) -> Estimate:
    """Estimate the full outage count of a sparse site from the count it saw (events seen by 2+ sensors of its own)."""
    if not SIZES[0] <= sensors <= SIZES[-1]:
        raise ValueError(f"sensors must be between {SIZES[0]} and {SIZES[-1]}: the curve was measured only in that range.")
    if observed_events < 0:
        raise ValueError("observed_events must be 0 or more.")
    if uptime is not None and not 0 <= uptime <= 1:
        raise ValueError("uptime must be between 0 and 1.")
    c, q10, q90, interp = curve(sensors)
    est = observed_events / c
    lo, hi = est / (1 + q90), est / (1 + q10)
    w = ["Estimate for Accra-like sites, calibrated on two dense sites in Accra only; not a utility record."]
    if observed_events < 10:
        w.append("Fewer than 10 observed events: single months are noisy; use a longer period.")
    if uptime is None:
        w.append("Uptime not given: the estimate assumes sensor uptime like the reference sites.")
    elif uptime < LOW_UPTIME:
        w.append("Low uptime: in simulation, a curve learned at uptime 0.8 underestimated the total by 12% (8 sensors) to 43% (3 sensors) at uptime 0.5.")
    if interp:
        w.append("Sensor count lies between measured sizes; the curve is interpolated.")
    return Estimate(sensors, observed_events, round(c, 4), round(est, 1), round(est - observed_events, 1),
                    [round(lo, 1), round(hi, 1)], interp, w)
