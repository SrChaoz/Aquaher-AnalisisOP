import io
import unittest

import pandas as pd

from ro_model import Config, analyze, calculate_measurement, demo_rows, load_excel, simulate_temperature, to_excel


def sample_rows(qp=(10, 9.8, 9.6, 8.0, 7.8), pressures=None):
    pressures = pressures or [200] * len(qp)
    return pd.DataFrame({
        "FechaHora": pd.date_range("2026-04-01 08:00", periods=len(qp), freq="2h"),
        "P_alta": pressures,
        "P_rechazo": [180] * len(qp),
        "Qp": qp,
        "Qr": [4] * len(qp),
        "TDS_alim": [1000] * len(qp),
        "Turb_alim": [0.4] * len(qp),
        "TDS_prod": [50] * len(qp),
        "Cond_prod": [100] * len(qp),
        "TDS_rech": [2000] * len(qp),
        "Turb_rech": [0.7] * len(qp),
    })


class ModelTests(unittest.TestCase):
    def test_demo_has_two_analyzable_cycles(self):
        result = analyze(demo_rows(), Config())
        self.assertEqual(result.operational["Ciclo"].nunique(), 2)
        self.assertFalse(result.baseline.empty)
        self.assertFalse(result.monitoring.empty)
        self.assertEqual(result.first_alerts["Ciclo"].tolist(), [1])

    def test_single_measurement_matches_cycle_calculation(self):
        result = analyze(sample_rows(), Config())
        point = result.operational.iloc[0]
        quick = calculate_measurement(10, 200, 180, 1000, 50, Config())
        for name in ("Jw", "Delta_pi", "NDP", "Aeff"):
            self.assertAlmostEqual(quick[name], point[name])

    def test_loads_original_excel_layout_and_fills_dates(self):
        raw = pd.DataFrame([[None] * 22 for _ in range(9)])
        raw.iloc[7, 0] = pd.Timestamp("2026-04-01")
        raw.iloc[7, 3] = "08:00:00"
        raw.iloc[8, 3] = "10:00:00"
        for row, qp in ((7, 10), (8, 9)):
            for col, val in {11: 200, 12: 180, 13: qp, 14: 4,
                             15: 1000, 17: 2, 18: 50, 19: 100,
                             20: 2000, 21: 0.7}.items():
                raw.iloc[row, col] = val
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            raw.to_excel(writer, sheet_name="DATA-OSMOSIS", header=False, index=False)
        result = load_excel(buffer.getvalue())
        self.assertEqual(len(result), 2)
        self.assertEqual(result["Qp"].tolist(), [10, 9])
        self.assertEqual(result["FechaHora"].iloc[1], pd.Timestamp("2026-04-01 10:00"))
        self.assertEqual(result["TDS_prod"].tolist(), [50, 50])
        self.assertEqual(result["Cond_prod"].tolist(), [100, 100])
        self.assertEqual(result["TDS_rech"].tolist(), [2000, 2000])
        self.assertEqual(result["Turb_rech"].tolist(), [0.7, 0.7])

    def test_calculates_physical_metrics_and_separates_cycles(self):
        rows = sample_rows()
        rows.loc[4, "FechaHora"] = pd.Timestamp("2026-04-02 08:00")
        result = analyze(rows, Config())
        op = result.operational
        self.assertEqual(op["Ciclo"].tolist(), [1, 1, 1, 1, 2])
        self.assertAlmostEqual(op["Jw"].iloc[0], 10 * 3600 / (96 * 37.2))
        self.assertAlmostEqual(op["NDP"].iloc[0], 190 - op["Delta_pi"].iloc[0])
        self.assertAlmostEqual(op["Aeff"].iloc[0], op["Jw"].iloc[0] / op["NDP"].iloc[0])

    def test_alert_requires_two_consecutive_candidates_after_baseline(self):
        result = analyze(sample_rows(), Config())
        points = result.monitoring
        self.assertEqual(points["Estado"].iloc[3], "VIGILANCIA FOULING")
        self.assertEqual(points["Estado"].iloc[4], "ALERTA FOULING")
        self.assertEqual(result.first_alerts["Ciclo"].tolist(), [1])

    def test_nonpositive_ndp_is_excluded_from_permeability(self):
        rows = sample_rows(pressures=[0] * 5)
        rows["P_rechazo"] = 0
        result = analyze(rows, Config())
        self.assertTrue(result.operational["Aeff"].isna().all())
        self.assertTrue(result.first_alerts.empty)

    def test_temperature_25_reproduces_observed_flow_and_export_has_sheets(self):
        result = analyze(sample_rows(), Config())
        sim, summary = simulate_temperature(result.operational, 1, [25, 30], Config())
        self.assertEqual(sim.loc[sim["Temperatura_C"] == 25, "Qp_sim_Ls"].tolist(), [10, 9.8, 9.6, 8, 7.8])
        self.assertGreater(summary.loc[summary["Temperatura_C"] == 30, "Qp_promedio_Ls"].iloc[0], 0)
        output = pd.ExcelFile(io.BytesIO(to_excel(result, sim, summary)))
        self.assertIn("Seguimiento", output.sheet_names)
        self.assertIn("Temperatura", output.sheet_names)


if __name__ == "__main__":
    unittest.main()
