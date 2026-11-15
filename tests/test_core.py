import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import pytest
from fastapi.testclient import TestClient
from outage_gap.core import estimate
from api.main import app

c = TestClient(app)


def test_three_sensors():
    r = estimate(3, 24, 0.8)
    assert abs(r.estimated_total - 24 / 0.3745) < 0.1 and r.estimated_missed > 30
    assert r.range_80[0] < r.estimated_total < r.range_80[1] and not r.interpolated


def test_more_sensors_miss_less():
    assert estimate(3, 30).estimated_missed > estimate(8, 30).estimated_missed > 0


def test_all_sizes_measured():
    shares = [estimate(k, 20).detection_share for k in range(3, 9)]
    assert shares == sorted(shares) and not any(estimate(k, 20).interpolated for k in range(3, 9))


@pytest.mark.parametrize("k", [2, 9, 12])
def test_out_of_range(k):
    with pytest.raises(ValueError):
        estimate(k, 5)


def test_bad_values():
    with pytest.raises(ValueError):
        estimate(3, -1)
    with pytest.raises(ValueError):
        estimate(3, 5, 1.5)


def test_warnings():
    w = estimate(3, 5, 0.5).warnings
    assert any("Low uptime" in x for x in w) and any("Fewer than 10" in x for x in w)


def test_zero_events():
    r = estimate(5, 0)
    assert r.estimated_total == 0 and r.range_80 == [0, 0]


def test_api_routes():
    assert c.get("/health").json()["sensor_counts_calibrated"] == [3, 4, 5, 6, 7, 8]
    r = c.post("/estimate", json={"sensors": 3, "observed_events": 24, "uptime": 0.8}).json()
    assert r["estimated_total"] == 64.1 and r["range_80"] == [34.5, 214.6]
    assert c.post("/estimate", json={"sensors": 2, "observed_events": 5}).status_code == 422
    assert c.post("/estimate", json={"sensors": 3, "observed_events": 5, "uptime": 1.5}).status_code == 422
    assert c.get("/").status_code == 200


def test_streamlit_screen():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(pathlib.Path(__file__).parent.parent / "streamlit_app.py")).run()
    assert not at.exception
    assert at.metric[0].value == "64.1"


def test_batch():
    from outage_gap.batch import run
    out = run(open(str(pathlib.Path(__file__).parent.parent / "examples_sites.csv")).read()).splitlines()
    assert len(out) == 6 and "64.1" in out[1] and "ERROR" in out[5]


def test_calibration_matches_two_sensor_rule():
    """The curve must come from the 2-of-k counting rule: share for 3 sensors near 0.34, not the any-one-sensor 0.61."""
    import json
    cal = json.load(open(pathlib.Path(__file__).parent.parent / "outage_gap" / "calibration.json"))
    assert 0.33 < cal["k"]["3"]["c"] < 0.42 and cal["k"]["3"]["c_any_one_sensor"] > 0.55


def test_counting_rule_script():
    from outage_gap.count_events import count_events
    import pandas as pd
    rows = []
    for dev in "abc":
        for i in range(10):
            rows.append(dict(device=dev, time=pd.Timestamp("2024-01-01") + pd.Timedelta(minutes=30 * i), on_battery=1 if (dev in "ab" and 2 <= i <= 4) or (dev == "c" and i == 8) else 0))
    r = count_events(pd.DataFrame(rows))
    assert r["events_2plus"] == 1 and r["events_1_only"] == 1 and r["sensors"] == 3


def test_plain_english_explanations():
    from outage_gap.core import plan
    from outage_gap.explain import explain_estimate, explain_plan
    e = explain_estimate(estimate(3, 24))
    assert "counted 24 outages" in e["headline"] and len(e["steps"]) == 3 and e["how_sure"]
    assert "very wide" in e["how_sure"]            # k=3 range is 0.54 to 3.35 times
    assert "sensors" in explain_plan(plan(0.5))["headline"]
