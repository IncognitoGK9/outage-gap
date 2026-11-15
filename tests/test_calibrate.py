import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from api.main import app
from outage_gap import demo
from outage_gap.calibrate import calibrate, curve_from_draws
from outage_gap.core import check_calibration, estimate, plan
from outage_gap.count_events import count_by_site

c = TestClient(app)


def test_shipped_curve_is_reproducible_from_shipped_draws():
    """The function that builds your own curve gives exactly the shipped curve when fed the shipped draws."""
    R = pd.read_csv(ROOT / "calibration" / "calibration_draws.csv")
    shipped = json.load(open(ROOT / "outage_gap" / "calibration.json"))
    assert curve_from_draws(R, shipped["source"], estimate_sizes=range(3, 9)) == shipped


def test_own_curve_on_dummy_dense_sites():
    cal = demo.own_curve()
    shares = [cal["k"][str(k)]["c"] for k in range(3, 9)]
    assert shares == sorted(shares) and 0.5 < shares[0] < 0.8 and shares[-1] < 1
    assert cal["n_sites"] == 2 and cal["n_site_months"] == 18 and cal["range_method"] == "other sites"
    assert 0.85 < cal["reference_uptime"] < 0.95
    assert check_calibration(cal)


def test_own_curve_changes_the_estimate():
    own = estimate(3, 24, 0.9, demo.own_curve())
    assert own.estimated_total < estimate(3, 24, 0.9).estimated_total      # dummy world detects more than Accra
    assert "own curve" in own.warnings[0]


def test_own_curve_beats_accra_curve_in_its_own_world():
    s = {r["site"]: r for r in demo.run()["summary"]}
    for site in ("DUMMY-sparse-3", "DUMMY-sparse-5", "DUMMY-sparse-8"):
        assert s[site]["mean_abs_error_pct_own_curve"] < 0.5 * s[site]["mean_abs_error_pct_accra_curve"]
        assert s[site]["mean_abs_error_pct_own_curve"] < s[site]["mean_abs_error_pct_raw_count"]


def test_own_curve_fails_in_a_different_world_and_says_nothing():
    """The documented limit: a different outage mix breaks the curve and no warning appears."""
    r = [x for x in demo.run()["rows"] if x["site"].endswith("smalloutages")]
    assert all(x["own_error_pct"] < -30 for x in r)
    w = estimate(3, 18, 0.9, demo.own_curve()).warnings
    assert not any("differs" in x for x in w)


def test_uptime_warning_with_own_curve():
    assert any("differs from the reference uptime" in x for x in estimate(3, 18, 0.5, demo.own_curve()).warnings)


def test_calibrate_needs_enough_data():
    small = demo.build()["dense"]
    small = small[small.site == "DUMMY-dense-1"]
    small = small[small.bin < "2023-03-01"]
    with pytest.raises(ValueError, match="usable site-months"):
        calibrate(small)
    with pytest.raises(ValueError, match="Columns not recognised"):
        calibrate(pd.DataFrame({"a": [1], "b": [2]}))


def test_calibrate_single_site_uses_time_split():
    one = demo.build()["dense"]
    one = one[one.site == "DUMMY-dense-1"]
    cal = calibrate(one, sizes=(3, 5), draws=5)
    assert cal["range_method"] == "earlier versus later months" and sorted(cal["k"]) == ["3", "5"]
    assert any("One dense site only" in w for w in cal["warnings"])


def test_count_by_site_periods():
    sparse = demo.build()["sparse"]
    assert len(count_by_site(sparse, "year")) == 4 and len(count_by_site(sparse, "quarter")) == 16
    with pytest.raises(ValueError):
        count_by_site(sparse, "week")


def test_plan():
    p = plan(0.8)
    assert p["sensors_needed"] == 12 and p["table"][-1]["sensors"] == 16     # from the saturation test
    assert plan(0.99)["sensors_needed"] is None and "No tested sensor count" in plan(0.99)["note"]
    assert plan(0.8, demo.own_curve())["sensors_needed"] == 5
    with pytest.raises(ValueError):
        plan(0)


def test_check_calibration_messages():
    for bad in ({}, {"k": {}}, {"k": {"x": {}}}, {"k": {"3": {"c": 0.4}}}, {"k": {"3": {"c": 0, "err_q10": 0, "err_q90": 0}}}):
        with pytest.raises(ValueError):
            check_calibration(bad)


def test_api_calibrate_then_estimate():
    dense = c.get("/demo/dense.csv").text
    r = c.post("/calibrate", files={"file": ("dense.csv", dense)}, data={"draws": "10", "sizes": "3,5,8"})
    assert r.status_code == 200
    j = r.json()
    assert sorted(j["calibration"]["k"]) == ["3", "5", "8"] and j["calibration_id"].startswith("c_")
    a = c.post("/estimate", json={"sensors": 3, "observed_events": 24, "calibration_id": j["calibration_id"]}).json()
    assert a["detection_share"] == j["calibration"]["k"]["3"]["c"]
    inline = c.post("/estimate", json={"sensors": 3, "observed_events": 24, "calibration": j["calibration"]}).json()
    assert inline["estimated_total"] == a["estimated_total"]
    assert c.get(f"/calibrations/{j['calibration_id']}").json()["k"].keys() == j["calibration"]["k"].keys()
    between = c.post("/estimate", json={"sensors": 4, "observed_events": 5, "calibration_id": j["calibration_id"]}).json()
    assert between["interpolated"] is True                                   # 4 lies between the measured 3 and 5
    assert c.post("/estimate", json={"sensors": 9, "observed_events": 5, "calibration_id": j["calibration_id"]}).status_code == 422


def test_api_errors_are_clear():
    assert c.post("/estimate", json={"sensors": 3, "observed_events": 5, "calibration_id": "nope"}).status_code == 404
    assert c.post("/estimate", json={"sensors": 3, "observed_events": 5, "calibration": {"k": {}}}).status_code == 422
    r = c.post("/calibrate", files={"file": ("x.csv", "a,b\n1,2\n")})
    assert r.status_code == 422 and "Columns not recognised" in r.json()["detail"]
    assert c.post("/count", files={"file": ("x.csv", "a,b\n1,2\n")}, data={"period": "all"}).status_code == 422
    assert c.get("/plan?target_share=2").status_code == 422
    assert c.get("/demo/sites/nothing.csv").status_code == 404


def test_api_batch_json_and_csv():
    b = c.post("/estimate/batch", json={"sites": [{"site": "a", "sensors": 3, "observed_events": 24}, {"sensors": 20, "observed_events": 3}]}).json()
    assert b[0]["estimated_total"] == 64.1 and "error" in b[1]
    t = c.post("/estimate/csv", files={"file": ("s.csv", "site,sensors,observed_events\nA,3,24\n")},
               data={"calibration_id": "demo"}).text
    assert "A,3,24" in t and "0.6631" in t


def test_api_raw_file_to_answer_and_dummy_sites():
    sites = c.get("/demo/sites").json()
    assert {s["role"] for s in sites} == {"dense", "sparse"}
    one = c.get("/demo/sites/DUMMY-sparse-5.csv").text
    r = c.post("/analyze", files={"file": ("s.csv", one)}, data={"period": "year", "calibration_id": "demo"}).json()
    assert len(r) == 1 and r[0]["site"] == "DUMMY-sparse-5" and r[0]["sensors"] == 5 and r[0]["estimated_total"] > r[0]["events_2plus"]
    run = c.get("/demo/run").json()
    assert len(run["rows"]) == 16 and len(run["summary"]) == 4
    assert c.get("/plan?target_share=0.8&calibration_id=demo").json()["sensors_needed"] == 5


def test_command_line():
    def cli(*a):
        return subprocess.run([sys.executable, "-m", "outage_gap", *a], cwd=ROOT, capture_output=True, text=True)
    r = cli("estimate", "examples_sites.csv")
    assert r.returncode == 0 and "64.1" in r.stdout
    assert "64.1" in cli("examples_sites.csv").stdout                       # short form still works
    assert "Sensors needed for a share of 0.8: 12" in cli("plan", "--target", "0.8").stdout
    bad = cli("analyze", "no_such_file.csv")
    assert bad.returncode != 0 and "Error" in bad.stderr


def test_streamlit_own_curve_flow():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=120).run()
    at.radio[0].set_value(at.radio[0].options[1]).run()                    # simple division screen
    assert not at.exception and at.metric[0].value == "64.1"
    next(x for x in at.checkbox if "dummy dense" in x.label).check()
    at.run()
    next(b for b in at.button if b.label == "Measure my curve").click()
    at.run()
    assert not at.exception and not at.error
    assert len(at.sidebar.radio[0].options) == 2                           # shipped curve + the new one
    at.sidebar.radio[0].set_value("My dense sites")
    at.run()
    assert not at.exception and at.metric[0].value == "36.2"               # own curve: 24 / 0.6631


def test_api_learned_estimate_and_analyze():
    r = c.post("/estimate/learned", json=dict(sensors=3, seen_by_1=30, seen_by_2=12, seen_by_3=4, uptime=0.85))
    assert r.status_code == 200 and r.json()["estimated_total"] >= 16 and r.json()["explanation"]["headline"]
    assert c.post("/estimate/learned", json=dict(sensors=2, seen_by_1=1, seen_by_2=1, uptime=0.85)).status_code == 422
    t = c.post("/analyze", files={"file": ("s.csv", demo.all_sparse_file(), "text/csv")}, data=dict(period="quarter")).json()
    assert all("learned" in x for x in t if "error" not in x)
    res = c.get("/demo/run").json()
    assert all(s["mean_abs_error_pct_learned"] is not None for s in res["summary"])
