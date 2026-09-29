import io
import json
import unittest

import pandas as pd
from fastapi.testclient import TestClient

from backend.main import app


def workbook():
    raw = pd.DataFrame([[None] * 22 for _ in range(12)])
    for row in range(7, 12):
        raw.iloc[row, 0] = pd.Timestamp("2026-04-01") if row == 7 else None
        raw.iloc[row, 3] = f"{8 + 2 * (row - 7):02d}:00:00"
        for col, value in {11: 150, 12: 100, 13: [20, 20, 20, 18, 17][row - 7],
                           14: 21, 15: 517, 16: 0.71, 17: 2,
                           18: 49.8, 19: 90.6, 20: 935, 21: 0.65}.items():
            raw.iloc[row, col] = value
    raw.iloc[6, 17:22] = ["DUR", "TDS", "COND", "TDS", "TURB"]
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        raw.to_excel(writer, index=False, header=False, sheet_name="DATA-OSMOSIS")
    return output.getvalue()


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health(self):
        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok"})

    def test_analyze_workbook(self):
        response = self.client.post("/api/analyze", files={"file": ("abril.xlsx", workbook())},
                                    data={"config": "{}"})
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["summary"]["operational_rows"], 5)
        self.assertEqual(data["summary"]["cycles"], 1)
        self.assertEqual(data["operational"][0]["TDS_prod"], 49.8)
        self.assertEqual(data["operational"][0]["TDS_rech"], 935)
        self.assertEqual(len(data["first_alerts"]), 1)

    def test_rejects_wrong_file_type_and_layout(self):
        invalid = self.client.post("/api/analyze", files={"file": ("data.txt", b"abc")},
                                   data={"config": "{}"})
        self.assertEqual(invalid.status_code, 400)
        self.assertIn(".xlsx", invalid.json()["detail"])

    def test_calculate_and_export(self):
        calc = self.client.post("/api/calculate", json={"qp_l_s": 20, "p_high_psi": 150,
                                                    "p_reject_psi": 100, "tds_feed_mg_l": 517,
                                                    "tds_product_mg_l": 49.8, "config": {}})
        self.assertEqual(calc.status_code, 200, calc.text)
        self.assertGreater(calc.json()["Aeff"], 0)
        export = self.client.post("/api/export", files={"file": ("abril.xlsx", workbook())},
                                  data={"config": "{}", "cycle": "1", "temperature": "30"})
        self.assertEqual(export.status_code, 200, export.text)
        self.assertIn("spreadsheetml", export.headers["content-type"])
        sheets = pd.ExcelFile(io.BytesIO(export.content)).sheet_names
        self.assertIn("Datos_calculados", sheets)
        self.assertIn("Temperatura", sheets)


if __name__ == "__main__":
    unittest.main()
