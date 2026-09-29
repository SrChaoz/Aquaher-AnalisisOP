"""HTTP API for the Aquaher reverse-osmosis model.

Uploads are processed in memory for each request; this module has no storage.
"""

from __future__ import annotations

import json
import math
from typing import Any
from zipfile import BadZipFile

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError

from ro_model import Config, analyze, calculate_measurement, load_excel, simulate_temperature, to_excel

MAX_UPLOAD_BYTES = 4_000_000
MAX_ROWS = 5_000
NO_STORE = {"Cache-Control": "no-store"}

app = FastAPI(title="Aquaher RO API", docs_url=None, redoc_url=None, openapi_url=None)


class ConfigInput(BaseModel):
    membranes: int = Field(default=96, ge=1, le=10_000)
    element_area_m2: float = Field(default=37.2, gt=0, le=1_000)
    reference_temp_c: float = Field(default=25, ge=-5, le=60)
    permeate_pressure_psi: float = Field(default=0, ge=0, le=500)
    max_gap_h: float = Field(default=4, gt=0, le=72)
    basal_quantile: float = Field(default=0.05, gt=0, lt=0.5)
    diagnostic_band_pct: float = Field(default=5, gt=0, le=50)

    def model_config_value(self) -> Config:
        return Config(**self.model_dump())


class CalculateInput(BaseModel):
    qp_l_s: float = Field(gt=0)
    p_high_psi: float = Field(ge=0)
    p_reject_psi: float = Field(ge=0)
    tds_feed_mg_l: float = Field(ge=0)
    tds_product_mg_l: float = Field(ge=0)
    config: ConfigInput = Field(default_factory=ConfigInput)


class SimulateInput(BaseModel):
    operational: list[dict[str, Any]]
    cycle: int = Field(ge=1)
    temperature_c: float = Field(ge=5, le=45)
    config: ConfigInput = Field(default_factory=ConfigInput)


def _config(raw: str) -> Config:
    try:
        return ConfigInput.model_validate_json(raw).model_config_value()
    except ValidationError as exc:
        raise HTTPException(422, "Parámetros del modelo inválidos.") from exc


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    clean = frame.copy()
    for name in clean.select_dtypes(include=["datetime64"]).columns:
        clean[name] = clean[name].dt.strftime("%Y-%m-%dT%H:%M:%S")
    return json.loads(clean.to_json(orient="records"))


async def _analyze_upload(file: UploadFile, config: Config):
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(400, "Selecciona un archivo .xlsx válido.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "El archivo supera el límite de 4 MB.")
    try:
        rows = load_excel(content)
        if len(rows) > MAX_ROWS:
            raise HTTPException(413, f"El archivo supera el límite de {MAX_ROWS:,} registros.")
        return rows, analyze(rows, config)
    except (ValueError, BadZipFile, OSError, KeyError, TypeError) as exc:
        raise HTTPException(400, f"No se pudo leer el archivo: {exc}") from exc


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze_file(file: UploadFile = File(...), config: str = Form("{}")):
    settings = _config(config)
    rows, result = await _analyze_upload(file, settings)
    payload = json.dumps({
            "summary": {
                "read_rows": len(rows),
                "operational_rows": len(result.operational),
                "cycles": int(result.operational["Ciclo"].nunique()),
                "alert_cycles": len(result.first_alerts),
                "invalid_ndp": result.excluded_ndp,
                "limit_a": result.limit_a if math.isfinite(result.limit_a) else None,
                "limit_ndp": result.limit_ndp if math.isfinite(result.limit_ndp) else None,
                "first_date": rows["FechaHora"].min().strftime("%Y-%m-%d"),
                "last_date": rows["FechaHora"].max().strftime("%Y-%m-%d"),
            },
            "cycles": _records(result.cycles),
            "operational": _records(result.operational),
            "monitoring": _records(result.monitoring),
            "first_alerts": _records(result.first_alerts),
        }, ensure_ascii=False, allow_nan=False)
    if len(payload.encode("utf-8")) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "El resultado supera el límite de respuesta de 4 MB.")
    return Response(content=payload, media_type="application/json", headers=NO_STORE)


@app.post("/api/calculate")
def calculate(body: CalculateInput):
    result = calculate_measurement(body.qp_l_s, body.p_high_psi, body.p_reject_psi,
                                   body.tds_feed_mg_l, body.tds_product_mg_l,
                                   body.config.model_config_value())
    return Response(content=json.dumps({k: v if math.isfinite(v) else None for k, v in result.items()}),
                    media_type="application/json", headers=NO_STORE)


@app.post("/api/simulate")
def simulate(body: SimulateInput):
    frame = pd.DataFrame(body.operational)
    if frame.empty or len(frame) > MAX_ROWS:
        raise HTTPException(400, "Selecciona un ciclo válido.")
    frame["FechaHora"] = pd.to_datetime(frame["FechaHora"], errors="coerce")
    try:
        points, summary = simulate_temperature(frame, body.cycle,
                                               [body.temperature_c], body.config.model_config_value())
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return Response(content=json.dumps({"points": _records(points), "summary": _records(summary)},
                                       ensure_ascii=False), media_type="application/json", headers=NO_STORE)


@app.post("/api/export")
async def export_file(file: UploadFile = File(...), config: str = Form("{}"),
                      cycle: int | None = Form(None), temperature: float = Form(30)):
    settings = _config(config)
    _, result = await _analyze_upload(file, settings)
    simulation = temperature_summary = None
    if cycle is not None:
        if not 5 <= temperature <= 45:
            raise HTTPException(400, "La temperatura debe estar entre 5 y 45 °C.")
        try:
            simulation, temperature_summary = simulate_temperature(result.operational, cycle,
                                                                    [temperature], settings)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    content = to_excel(result, simulation, temperature_summary)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "El resultado supera el límite de descarga de Vercel.")
    return Response(content=content,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={**NO_STORE, "Content-Disposition": 'attachment; filename="Resultados_Aquaher_RO.xlsx"'})
