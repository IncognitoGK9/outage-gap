"""FastAPI service. Run from the repository root: uvicorn api.main:app --port 8000   (interactive docs at /docs)"""
import collections
import hashlib
import io
import json
import pathlib
from dataclasses import asdict
from typing import List, Optional

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Query as QParam, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from outage_gap import batch, demo
from outage_gap.calibrate import calibrate as run_calibrate
from outage_gap.core import CAL, SIZES, check_calibration, estimate, plan
from outage_gap.count_events import PERIODS, count_by_site

MAX_UPLOAD_MB = 60
MAX_DRAWS = 100
STORE_LIMIT = 50

app = FastAPI(title="OutageGap", version="0.2.0",
              description="Estimate outages that sparse plug-in sensor sites miss. Ships a curve measured in Accra, and lets "
                          "you measure your own from dense sites. Research prototype; not a utility record.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Calibrations made through /calibrate are kept in memory only (lost when the service restarts).
# Send the calibration itself in the request ('calibration') to be independent of this.
STORE = collections.OrderedDict()


def _put(cal):
    cid = "c_" + hashlib.sha1(json.dumps(cal, sort_keys=True).encode()).hexdigest()[:10]
    STORE[cid] = cal
    STORE.move_to_end(cid)
    while len(STORE) > STORE_LIMIT:
        STORE.popitem(last=False)
    return cid


def _resolve(calibration_id=None, calibration=None):
    """Return the calibration to use: inline > id > None (the shipped Accra curve)."""
    try:
        if calibration is not None:
            return check_calibration(calibration)
        if calibration_id in (None, "", "accra"):
            return None
        if calibration_id == "demo":
            return demo.own_curve()
        if calibration_id in STORE:
            return STORE[calibration_id]
    except ValueError as e:
        raise HTTPException(422, str(e))
    raise HTTPException(404, f"Unknown calibration_id '{calibration_id}'. Calibrations are kept in memory only: "
                             "run POST /calibrate again, or send the calibration inline in the 'calibration' field. "
                             "Use 'demo' for the dummy-site curve, or leave it out for the shipped Accra curve.")


async def _read_csv(file: UploadFile) -> pd.DataFrame:
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File is larger than {MAX_UPLOAD_MB} MB. Use the command line for large files: "
                                 "python -m outage_gap calibrate file.csv")
    try:
        return pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        raise HTTPException(422, f"Could not read the file as CSV: {e}")


class Query(BaseModel):
    sensors: int = Field(..., description="Number of sensors at the site (3 to 8 for the shipped curve).")
    observed_events: int = Field(..., ge=0, description="Outage events seen by at least 2 sensors in the period.")
    uptime: Optional[float] = Field(None, ge=0, le=1, description="Share of time the site's sensors were reporting (optional).")
    calibration_id: Optional[str] = Field(None, description="Id returned by /calibrate, or 'demo'. Omit for the Accra curve.")
    calibration: Optional[dict] = Field(None, description="A whole calibration (as returned by /calibrate). Overrides calibration_id.")


class Answer(BaseModel):
    sensors: int
    observed_events: int
    detection_share: float
    estimated_total: float
    estimated_missed: float
    range_80: List[float]
    interpolated: bool
    curve: str
    warnings: List[str]


class SiteQuery(BaseModel):
    site: Optional[str] = None
    sensors: int
    observed_events: int = Field(..., ge=0)
    uptime: Optional[float] = Field(None, ge=0, le=1)


class BatchQuery(BaseModel):
    sites: List[SiteQuery]
    calibration_id: Optional[str] = None
    calibration: Optional[dict] = None


@app.get("/health", tags=["info"])
def health():
    return {"status": "ok", "version": app.version, "calibration": CAL["source"], "sensor_counts_calibrated": SIZES,
            "stored_calibrations": len(STORE)}


@app.get("/curve", tags=["info"])
def get_curve(calibration_id: Optional[str] = None):
    """The detection curve in use: the shipped Accra curve, or one from /calibrate."""
    return _resolve(calibration_id) or CAL


@app.post("/estimate", response_model=Answer, tags=["estimate"])
def post_estimate(q: Query):
    """One site: counted events and sensor count in, estimated total and 80% range out."""
    cal = _resolve(q.calibration_id, q.calibration)
    try:
        return asdict(estimate(q.sensors, q.observed_events, q.uptime, cal))
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/estimate/batch", tags=["estimate"])
def post_estimate_batch(b: BatchQuery):
    """Many sites in one JSON call. A bad row gets an 'error' entry; the other rows are still answered."""
    cal = _resolve(b.calibration_id, b.calibration)
    out = []
    for i, s in enumerate(b.sites):
        try:
            out.append(dict(site=s.site or f"row{i + 1}", **asdict(estimate(s.sensors, s.observed_events, s.uptime, cal))))
        except ValueError as e:
            out.append(dict(site=s.site or f"row{i + 1}", error=str(e)))
    return out


@app.post("/estimate/csv", response_class=PlainTextResponse, tags=["estimate"])
async def post_estimate_csv(file: UploadFile = File(..., description="CSV: site,sensors,observed_events[,uptime]"),
                            calibration_id: Optional[str] = Form(None)):
    """Many sites from a CSV file; the answer is a CSV file."""
    cal = _resolve(calibration_id)
    raw = (await file.read()).decode("utf-8", errors="replace")
    return PlainTextResponse(batch.run(raw, cal), media_type="text/csv")


@app.post("/count", tags=["from raw sensor files"])
async def post_count(file: UploadFile = File(..., description="Raw readings or nLine 30-minute bins; optional 'site' column"),
                     period: str = Form("all", description="all, month, quarter or year")):
    """Count outage events (seen by 2+ sensors) per site and period from a raw sensor file."""
    df = await _read_csv(file)
    try:
        return count_by_site(df, period)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/analyze", tags=["from raw sensor files"])
async def post_analyze(file: UploadFile = File(..., description="Raw sensor file of sparse sites; optional 'site' column"),
                       period: str = Form("quarter", description="all, month, quarter or year"),
                       calibration_id: Optional[str] = Form(None)):
    """From a raw sensor file to the answer: count events per site and period, then estimate the total and missed outages."""
    cal = _resolve(calibration_id)
    df = await _read_csv(file)
    try:
        rows = count_by_site(df, period)
    except ValueError as e:
        raise HTTPException(422, str(e))
    out = []
    for r in rows:
        try:
            out.append({**r, **asdict(estimate(r["sensors"], r["events_2plus"], r["uptime_estimate"], cal))})
        except ValueError as e:
            out.append({**r, "error": str(e)})
    return out


@app.post("/calibrate", tags=["your own curve"])
async def post_calibrate(file: UploadFile = File(..., description="Raw sensor file of DENSE sites (many sensors per site)"),
                         sizes: str = Form("3,4,5,6,7,8", description="Sensor counts to measure, comma separated"),
                         draws: int = Form(40, ge=1, le=MAX_DRAWS, description="Random subsets per site-month and size"),
                         seed: int = Form(1),
                         min_sensors: int = Form(8, ge=3, description="A dense site-month needs at least this many sensors"),
                         min_coverage: float = Form(0.6, gt=0, le=1, description="...each reporting in this share of 30-minute bins")):
    """Measure your own detection curve from your dense sites. Returns the curve and a calibration_id to use in the other calls.

    Large files take minutes. Use the command line for big data. The id is kept in memory only; keep the returned
    calibration to send inline, or save it as a file and use it with the command line.
    """
    df = await _read_csv(file)
    try:
        ks = [int(x) for x in sizes.replace(" ", "").split(",") if x]
        cal = run_calibrate(df, ks, draws, seed, min_sensors, min_coverage)
    except ValueError as e:
        raise HTTPException(422, str(e))
    cid = _put(cal)
    summary = [dict(sensors=int(k), detection_share=p["c"], range_10_90_pct=[round(100 * p["err_q10"]), round(100 * p["err_q90"])],
                    median_single_month_error=p["median_abs_err"]) for k, p in cal["k"].items()]
    return dict(calibration_id=cid, calibration=cal, summary=summary, warnings=cal["warnings"])


@app.get("/calibrations/{calibration_id}", tags=["your own curve"])
def get_calibration(calibration_id: str):
    """Fetch a calibration kept in memory."""
    return _resolve(calibration_id) or CAL


@app.get("/plan", tags=["plan"])
def get_plan(target_share: float = QParam(0.7, gt=0, le=1, description="Share of the reference outages the site should count"),
             calibration_id: Optional[str] = None):
    """How many sensors does a site need to count at least `target_share` of the outages the dense reference saw?"""
    try:
        return plan(target_share, _resolve(calibration_id))
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/demo/sites", tags=["dummy sites"])
def demo_sites():
    """Dummy (synthetic) sites with known truth, for trying the API without real data."""
    return demo.catalog()


@app.get("/demo/sites/{site}.csv", response_class=PlainTextResponse, tags=["dummy sites"])
def demo_site_csv(site: str):
    """The raw sensor file of one dummy site. Upload it to /calibrate (dense sites) or /analyze (sparse sites)."""
    try:
        return PlainTextResponse(demo.site_file(site), media_type="text/csv")
    except KeyError:
        raise HTTPException(404, f"No dummy site '{site}'. See GET /demo/sites.")


@app.get("/demo/dense.csv", response_class=PlainTextResponse, tags=["dummy sites"])
def demo_dense():
    return PlainTextResponse(demo.all_dense_file(), media_type="text/csv")


@app.get("/demo/sparse.csv", response_class=PlainTextResponse, tags=["dummy sites"])
def demo_sparse():
    return PlainTextResponse(demo.all_sparse_file(), media_type="text/csv")


@app.get("/demo/run", tags=["dummy sites"])
def demo_run():
    """Whole pipeline on the dummy sites, compared with the known truth: raw count, shipped Accra curve, own curve."""
    return demo.run()


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home():
    return (pathlib.Path(__file__).parent / "demo.html").read_text()
