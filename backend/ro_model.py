"""Reproducible calculations from the supplied Aquaher RO notebook.

The detector is exploratory. It is not a validated plant alarm or a control action.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from io import BytesIO
from typing import Iterable
import re

import numpy as np
import pandas as pd


NUMERIC = ["P_alta", "P_rechazo", "Qp", "Qr", "TDS_alim", "Turb_alim",
           "TDS_prod", "Cond_prod", "TDS_rech", "Turb_rech"]
EXCEL_COLUMNS = {"Fecha": 0, "Hora": 3, "P_alta": 11, "P_rechazo": 12,
                 "Qp": 13, "Qr": 14, "TDS_alim": 15, "Turb_alim": 16,
                 "TDS_prod": 18, "Cond_prod": 19, "TDS_rech": 20,
                 "Turb_rech": 21}


@dataclass(frozen=True)
class Config:
    membranes: int = 96
    element_area_m2: float = 37.2
    reference_temp_c: float = 25.0
    permeate_pressure_psi: float = 0.0
    max_gap_h: float = 4.0
    basal_quantile: float = 0.05
    diagnostic_band_pct: float = 5.0

    def __post_init__(self):
        if self.membranes <= 0 or self.element_area_m2 <= 0:
            raise ValueError("El número y el área de las membranas deben ser positivos.")
        if self.max_gap_h <= 0 or not 0 < self.basal_quantile < 1:
            raise ValueError("Revise la separación de ciclos y el percentil basal.")


@dataclass
class Analysis:
    operational: pd.DataFrame
    cycles: pd.DataFrame
    baseline: pd.DataFrame
    monitoring: pd.DataFrame
    first_alerts: pd.DataFrame
    limit_a: float
    limit_ndp: float
    excluded_ndp: int


def demo_rows() -> pd.DataFrame:
    """Synthetic points solely for learning the UI; never plant observations."""
    timestamps = list(pd.date_range("2026-04-01 08:00", periods=5, freq="2h"))
    timestamps += list(pd.date_range("2026-04-02 08:00", periods=5, freq="2h"))
    return pd.DataFrame({
        "FechaHora": timestamps,
        "P_alta": [200] * 10,
        "P_rechazo": [180] * 10,
        "Qp": [10, 9.9, 9.8, 8.4, 8.1, 10.2, 10.1, 10.0, 10.05, 10.1],
        "Qr": [4] * 10,
        "TDS_alim": [1000] * 10,
        "Turb_alim": [0.4] * 10,
        "TDS_prod": [50] * 10,
        "Cond_prod": [100] * 10,
        "TDS_rech": [2000] * 10,
        "Turb_rech": [0.7] * 10,
    })


def _date(value):
    if pd.isna(value):
        return pd.NaT
    if isinstance(value, (int, float, np.number)):
        return pd.to_datetime(value, unit="D", origin="1899-12-30", errors="coerce")
    return pd.to_datetime(value, errors="coerce")


def _time_delta(value):
    if pd.isna(value):
        return pd.NaT
    if isinstance(value, (datetime, time)):
        return pd.to_timedelta(value.hour * 3600 + value.minute * 60 + value.second
                               + value.microsecond / 1_000_000, unit="s")
    if isinstance(value, timedelta):
        return pd.Timedelta(value)
    if isinstance(value, (int, float, np.number)):
        return pd.to_timedelta(float(value), unit="D" if 0 <= value < 1 else "s")
    text = str(value).strip()
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}(?:\.\d+)?))?", text)
    if match:
        hours, minutes, seconds = match.groups()
        return pd.to_timedelta(int(hours) * 3600 + int(minutes) * 60 + float(seconds or 0), unit="s")
    return pd.NaT


def load_excel(source: bytes | BytesIO, sheet_name: str = "DATA-OSMOSIS") -> pd.DataFrame:
    """Read the fixed original worksheet layout (data begin at Excel row 8)."""
    try:
        raw = pd.read_excel(BytesIO(source) if isinstance(source, bytes) else source,
                            sheet_name=sheet_name, header=None)
    except ValueError as exc:
        raise ValueError(f"No se encontró la hoja «{sheet_name}».") from exc
    if raw.shape[1] < 22:
        raise ValueError("La hoja necesita al menos 22 columnas (A:V), como el formato original.")
    if len(raw) < 8:
        raise ValueError("La hoja no contiene registros desde la fila 8.")
    df = pd.DataFrame({name: raw.iloc[7:, position].to_numpy()
                       for name, position in EXCEL_COLUMNS.items()})
    df["Fecha"] = df["Fecha"].map(_date).ffill()
    df["FechaHora"] = df["Fecha"].dt.normalize() + df["Hora"].map(_time_delta)
    for column in NUMERIC:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["FechaHora"]).sort_values("FechaHora").reset_index(drop=True)
    if df.empty:
        raise ValueError("No hay filas con fecha y hora válidas en la hoja.")
    return df


def osmotic_pressure_psi(tds_mg_l, temp_c):
    return 2.0 * ((tds_mg_l / 1000.0) / 58.44) * 0.082057 * (temp_c + 273.15) * 14.6959


def calculate_measurement(qp_l_s: float, p_high_psi: float, p_reject_psi: float,
                          tds_feed_mg_l: float, tds_product_mg_l: float,
                          config: Config = Config()) -> dict[str, float]:
    """Explain one observed point without implying a fouling diagnosis."""
    if qp_l_s <= 0 or min(tds_feed_mg_l, tds_product_mg_l) < 0:
        raise ValueError("Qp debe ser positivo y los TDS no pueden ser negativos.")
    jw = qp_l_s * 3600 / (config.membranes * config.element_area_m2)
    delta_pi = osmotic_pressure_psi(tds_feed_mg_l, config.reference_temp_c) - osmotic_pressure_psi(
        tds_product_mg_l, config.reference_temp_c)
    ndp = (p_high_psi + p_reject_psi) / 2 - config.permeate_pressure_psi - delta_pi
    return {"Jw": jw, "Delta_pi": delta_pi, "NDP": ndp,
            "Aeff": jw / ndp if ndp > 0 else np.nan}


def _diagnosis(delta_ndp, delta_a, band):
    if pd.isna(delta_ndp) or pd.isna(delta_a):
        return "Datos insuficientes"
    if delta_a <= -band and abs(delta_ndp) <= band:
        return "Predominio de pérdida de permeabilidad"
    if delta_ndp <= -band and abs(delta_a) <= band:
        return "Predominio operacional"
    if delta_a <= -band and delta_ndp <= -band:
        return "Mixto"
    if delta_a <= -band and delta_ndp > band:
        return "Aeff cae pese a aumento de NDP"
    if abs(delta_a) <= band and abs(delta_ndp) <= band:
        return "Estable / cambios pequeños"
    return "Otro comportamiento"


def analyze(rows: pd.DataFrame, config: Config = Config()) -> Analysis:
    """Calculate physical metrics, cycle summaries and exploratory fouling states."""
    required = {"FechaHora", "P_alta", "P_rechazo", "Qp", "TDS_alim", "TDS_prod"}
    missing = required - set(rows.columns)
    if missing:
        raise ValueError("Faltan columnas: " + ", ".join(sorted(missing)))
    op = rows.copy()
    op["FechaHora"] = pd.to_datetime(op["FechaHora"], errors="coerce")
    for column in NUMERIC:
        if column not in op:
            op[column] = np.nan
        op[column] = pd.to_numeric(op[column], errors="coerce")
    op = op.loc[op["FechaHora"].notna() & (op["Qp"] > 0)].sort_values("FechaHora").reset_index(drop=True)
    if op.empty:
        raise ValueError("No hay registros operativos con fecha, hora y Qp > 0.")
    op["gap_h"] = op["FechaHora"].diff().dt.total_seconds() / 3600
    op["Ciclo"] = (op["gap_h"].isna() | (op["gap_h"] > config.max_gap_h)).cumsum().astype(int)
    op["tau_h"] = op.groupby("Ciclo")["FechaHora"].transform(
        lambda dates: (dates - dates.iloc[0]).dt.total_seconds() / 3600)
    op["Jw"] = op["Qp"] * 3600 / (config.membranes * config.element_area_m2)
    op["pi_alim"] = osmotic_pressure_psi(op["TDS_alim"], config.reference_temp_c)
    op["pi_prod"] = osmotic_pressure_psi(op["TDS_prod"], config.reference_temp_c)
    op["Delta_pi"] = op["pi_alim"] - op["pi_prod"]
    op["P_media"] = (op["P_alta"] + op["P_rechazo"]) / 2
    op["NDP"] = op["P_media"] - config.permeate_pressure_psi - op["Delta_pi"]
    invalid_ndp = op["NDP"].notna() & (op["NDP"] <= 0)
    op["Aeff"] = op["Jw"] / op["NDP"].where(op["NDP"] > 0)
    ref_a = op.groupby("Ciclo")["Aeff"].transform(lambda s: s.dropna().head(3).median())
    op["Aref"] = ref_a
    op["AN"] = op["Aeff"] / op["Aref"].where(op["Aref"] > 0)

    cycle_rows = []
    baseline_rows = []
    for cycle, group in op.groupby("Ciclo", sort=True):
        valid = group.dropna(subset=["Qp", "NDP", "Aeff"]).sort_values("FechaHora")
        if valid.empty:
            continue
        first, last = valid.iloc[0], valid.iloc[-1]
        x, y = valid["tau_h"].to_numpy(), valid["Qp"].to_numpy()
        if len(valid) >= 2 and len(np.unique(x)) >= 2:
            slope, intercept = np.polyfit(x, y, 1)
            total = np.sum((y - np.mean(y)) ** 2)
            r2 = 1 - np.sum((y - (intercept + slope * x)) ** 2) / total if total > 0 else np.nan
        else:
            slope = intercept = r2 = np.nan
        d_qp = 100 * (last.Qp / first.Qp - 1)
        d_ndp = 100 * (last.NDP / first.NDP - 1)
        d_a = 100 * (last.Aeff / first.Aeff - 1)
        cycle_rows.append({"Ciclo": cycle, "n": len(valid), "Inicio": first.FechaHora,
                           "Fin": last.FechaHora, "Duracion_h": last.tau_h,
                           "Qp0": first.Qp, "Qpf": last.Qp, "NDP0": first.NDP,
                           "NDPf": last.NDP, "Aeff0": first.Aeff, "Aefff": last.Aeff,
                           "beta0": intercept, "beta1_Ls_h": slope, "R2": r2,
                           "Delta_Qp_pct": d_qp, "Delta_NDP_pct": d_ndp,
                           "Delta_Aeff_pct": d_a,
                           "Diagnostico": _diagnosis(d_ndp, d_a, config.diagnostic_band_pct)})
        if len(valid) >= 3:
            early = valid.head(3)
            a_ref, ndp_ref = early["Aeff"].median(), early["NDP"].median()
            if a_ref > 0 and ndp_ref > 0:
                for _, point in early.iterrows():
                    baseline_rows.append({"Ciclo": cycle, "AN_base": point.Aeff / a_ref,
                                          "NDP_N_base": point.NDP / ndp_ref})
    cycles = pd.DataFrame(cycle_rows)
    baseline = pd.DataFrame(baseline_rows, columns=["Ciclo", "AN_base", "NDP_N_base"])
    if baseline.empty:
        limit_a = limit_ndp = np.nan
    else:
        limit_a = float(baseline["AN_base"].quantile(config.basal_quantile))
        limit_ndp = float(baseline["NDP_N_base"].quantile(config.basal_quantile))

    monitored = []
    first_alerts = []
    for cycle, group in op.groupby("Ciclo", sort=True):
        valid = group.dropna(subset=["Aeff", "NDP", "Qp"]).sort_values("FechaHora").copy()
        if len(valid) < 4 or not np.isfinite(limit_a) or not np.isfinite(limit_ndp):
            continue
        a_ref, ndp_ref = valid["Aeff"].head(3).median(), valid["NDP"].head(3).median()
        if a_ref <= 0 or ndp_ref <= 0:
            continue
        valid["AN_alerta"] = valid["Aeff"] / a_ref
        valid["NDP_N_alerta"] = valid["NDP"] / ndp_ref
        valid["evaluable"] = np.arange(len(valid)) >= 3
        valid["candidato_fouling"] = (valid["evaluable"] & (valid["AN_alerta"] < limit_a)
                                       & (valid["NDP_N_alerta"] >= limit_ndp))
        valid["ALERTA_FOULING"] = (valid["candidato_fouling"]
                                   & valid["candidato_fouling"].shift(fill_value=False))
        valid["Estado"] = "NORMAL / SIN ALERTA"
        operational_change = (valid["evaluable"] & (valid["NDP_N_alerta"] < limit_ndp)
                              & (valid["AN_alerta"] >= limit_a))
        valid.loc[operational_change, "Estado"] = "CAMBIO OPERACIONAL"
        valid.loc[valid["candidato_fouling"], "Estado"] = "VIGILANCIA FOULING"
        valid.loc[valid["ALERTA_FOULING"], "Estado"] = "ALERTA FOULING"
        monitored.append(valid)
        alerts = valid.loc[valid["ALERTA_FOULING"]]
        if not alerts.empty:
            point = alerts.iloc[0]
            first_alerts.append({"Ciclo": cycle, "Hora_alerta_desde_inicio_h": point.tau_h,
                                 "FechaHora_alerta": point.FechaHora,
                                 "AN_en_alerta": point.AN_alerta,
                                 "NDP_N_en_alerta": point.NDP_N_alerta,
                                 "Qp_en_alerta_Ls": point.Qp})
    monitoring = pd.concat(monitored, ignore_index=True) if monitored else pd.DataFrame()
    return Analysis(op, cycles, baseline, monitoring, pd.DataFrame(first_alerts),
                    limit_a, limit_ndp, int(invalid_ndp.sum()))


def temperature_correction(temp_c: float) -> float:
    if np.isclose(temp_c, 25.0):
        return 1.0
    energy = 25000.0 if temp_c > 25 else 20000.0
    return float(np.exp((energy / 8.314) * (1 / 298.15 - 1 / (temp_c + 273.15))))


def simulate_temperature(operational: pd.DataFrame, cycle: int,
                         temperatures: Iterable[float], config: Config = Config()):
    group = operational.loc[operational["Ciclo"] == cycle].dropna(
        subset=["Qp", "NDP", "Delta_pi", "TDS_alim", "TDS_prod"]).copy()
    if group.empty:
        raise ValueError("El ciclo elegido no tiene datos suficientes para simular temperatura.")
    temperatures = list(dict.fromkeys([config.reference_temp_c, *temperatures]))
    frames = []
    for temp in temperatures:
        if not -5 <= temp <= 60:
            raise ValueError("La temperatura simulada debe estar entre -5 y 60 °C.")
        delta_pi = osmotic_pressure_psi(group["TDS_alim"], temp) - osmotic_pressure_psi(group["TDS_prod"], temp)
        ndp_temp = group["NDP"] + group["Delta_pi"] - delta_pi
        tcf_ratio = temperature_correction(temp) / temperature_correction(config.reference_temp_c)
        qp_temp = group["Qp"] * tcf_ratio * (ndp_temp / group["NDP"])
        frames.append(pd.DataFrame({"FechaHora": group["FechaHora"].to_numpy(),
                                    "tau_h": group["tau_h"].to_numpy(),
                                    "Temperatura_C": temp, "TCF_relativo": tcf_ratio,
                                    "Delta_pi_psi": delta_pi.to_numpy(),
                                    "NDP_psi": ndp_temp.to_numpy(),
                                    "Qp_sim_Ls": qp_temp.where(ndp_temp > 0).to_numpy()}))
    sim = pd.concat(frames, ignore_index=True)
    summary = sim.groupby("Temperatura_C", as_index=False).agg(
        TCF_relativo=("TCF_relativo", "first"), Qp_inicio_Ls=("Qp_sim_Ls", "first"),
        Qp_final_Ls=("Qp_sim_Ls", "last"), Qp_promedio_Ls=("Qp_sim_Ls", "mean"),
        NDP_inicio_psi=("NDP_psi", "first"), NDP_final_psi=("NDP_psi", "last"))
    base = summary.loc[summary["Temperatura_C"] == config.reference_temp_c, "Qp_promedio_Ls"].iloc[0]
    summary["Incremento_Qp_prom_vs_base_pct"] = 100 * (summary["Qp_promedio_Ls"] / base - 1)
    return sim, summary


def to_excel(analysis: Analysis, simulation: pd.DataFrame | None = None,
             temperature_summary: pd.DataFrame | None = None) -> bytes:
    output = BytesIO()
    sheets = {"Datos_calculados": analysis.operational, "Ciclos": analysis.cycles,
              "Calibracion_basal": analysis.baseline,
              "Seguimiento": analysis.monitoring, "Primeras_alertas": analysis.first_alerts}
    if simulation is not None:
        sheets["Temperatura"] = simulation
    if temperature_summary is not None:
        sheets["Resumen_temperatura"] = temperature_summary
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return output.getvalue()
