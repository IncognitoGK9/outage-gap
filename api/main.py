"""FastAPI service. Run from the repository root: uvicorn api.main:app --port 8000"""
import pathlib
from dataclasses import asdict
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from outage_gap.core import CAL, SIZES, estimate

app = FastAPI(title="OutageGap", version="0.1.0",
              description="Research prototype. Calibrated on Accra only. Not a utility record.")


class Query(BaseModel):
    sensors: int = Field(..., description="Number of sensors at the site (3 to 8).")
    observed_events: int = Field(..., ge=0, description="Outage events seen by at least 2 sensors in the period.")
    uptime: Optional[float] = Field(None, ge=0, le=1, description="Share of time the site's sensors were reporting (optional).")


class Answer(BaseModel):
    sensors: int
    observed_events: int
    detection_share: float
    estimated_total: float
    estimated_missed: float
    range_80: List[float]
    interpolated: bool
    warnings: List[str]


@app.get("/health")
def health():
    return {"status": "ok", "calibration": CAL["source"], "sensor_counts_calibrated": SIZES}


@app.get("/curve")
def get_curve():
    return CAL


@app.post("/estimate", response_model=Answer)
def post_estimate(q: Query):
    try:
        return asdict(estimate(q.sensors, q.observed_events, q.uptime))
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def demo():
    return (pathlib.Path(__file__).parent / "demo.html").read_text()
