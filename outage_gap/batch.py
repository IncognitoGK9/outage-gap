"""Batch use: a CSV with columns site, sensors, observed_events (and optional uptime) -> estimates for every row."""
import csv
import io
from .core import estimate

FIELDS = ["site", "sensors", "observed_events", "uptime", "detection_share", "estimated_total",
          "estimated_missed", "low_80", "high_80", "interpolated", "warnings"]


def run(text: str) -> str:
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=FIELDS, lineterminator="\n")
    w.writeheader()
    for i, row in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        site = row.get("site") or f"row{i}"
        try:
            up = row.get("uptime")
            r = estimate(int(row["sensors"]), int(row["observed_events"]), float(up) if up not in (None, "") else None)
            w.writerow(dict(site=site, sensors=r.sensors, observed_events=r.observed_events, uptime=up or "",
                            detection_share=r.detection_share, estimated_total=r.estimated_total,
                            estimated_missed=r.estimated_missed, low_80=r.range_80[0], high_80=r.range_80[1],
                            interpolated=r.interpolated, warnings=" | ".join(r.warnings)))
        except (ValueError, KeyError) as e:
            w.writerow(dict(site=site, sensors=row.get("sensors", ""), observed_events=row.get("observed_events", ""),
                            warnings=f"ERROR row {i}: {e}"))
    return out.getvalue()
