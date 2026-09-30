"""Tests: schema conformance of examples + a sample report (jsonschema)."""

import glob
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from jsonschema import Draft202012Validator  # noqa: E402


def load_schema():
    with open(os.path.join(ROOT, "schema", "ecological-sensor-reading.schema.json"),
              encoding="utf-8") as f:
        return json.load(f)


def readings_from(doc):
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict) and isinstance(doc.get("readings"), list):
        return doc["readings"]
    if isinstance(doc, dict) and "sensor_id" in doc:
        return [doc]
    raise ValueError("not a reading / list / readings-doc")


class TestSchemaConformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = Draft202012Validator(load_schema())

    def test_examples_exist(self):
        files = sorted(glob.glob(os.path.join(ROOT, "examples", "*.json")))
        self.assertGreaterEqual(len(files), 3,
                                "need at least 3 example JSON files")

    def test_all_examples_conform(self):
        for path in sorted(glob.glob(os.path.join(ROOT, "examples", "*.json"))):
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
            readings = readings_from(doc)
            self.assertGreater(len(readings), 0, f"{path}: no readings")
            for i, r in enumerate(readings):
                errs = list(self.validator.iter_errors(r))
                self.assertEqual(errs, [],
                                 f"{path} reading[{i}]: {[e.message for e in errs]}")

    def test_sample_run_output_conforms(self):
        path = os.path.join(ROOT, "examples", "baton-rouge-sample-run.json")
        self.assertTrue(os.path.exists(path), "sample run output missing")
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        readings = readings_from(doc)
        self.assertGreater(len(readings), 3)
        ids = [r["sensor_id"] for r in readings]
        self.assertTrue(any(i.startswith("VIRTUAL:") for i in ids),
                        "sample run must include the virtual placement reading")
        for i, r in enumerate(readings):
            errs = list(self.validator.iter_errors(r))
            self.assertEqual(errs, [],
                             f"sample run reading[{i}]: {[e.message for e in errs]}")

    def test_report_has_recommendation_and_gap(self):
        path = os.path.join(ROOT, "examples", "baton-rouge-sample-run.json")
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        rec = doc["recommendation"]
        self.assertIn("lat", rec)
        self.assertIn("lon", rec)
        self.assertTrue(rec["rationale"])
        self.assertIn("gap_analysis", doc)


if __name__ == "__main__":
    unittest.main()
