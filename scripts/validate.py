"""Validate sensor-gap JSON outputs against the #450 ecological sensor schema.

Usage: python scripts/validate.py [path ...]
With no paths, validates examples/*.json and reports readings counts.
A file may be a single reading, a list of readings, or an object with a
"readings" array (sensor-gap report / example format).
"""

import glob
import json
import os
import sys

from jsonschema import Draft202012Validator

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(ROOT, "schema", "ecological-sensor-reading.schema.json")


def load_schema():
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def iter_readings(doc):
    if isinstance(doc, list):
        yield from doc
    elif isinstance(doc, dict) and isinstance(doc.get("readings"), list):
        yield from doc["readings"]
    elif isinstance(doc, dict) and "sensor_id" in doc:
        yield doc
    else:
        raise ValueError("file is neither a reading, a list, nor has 'readings'")


def validate_paths(paths):
    schema = load_schema()
    validator = Draft202012Validator(schema)
    total, failed = 0, 0
    for path in paths:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        try:
            readings = list(iter_readings(doc))
        except ValueError as e:
            print(f"FAIL {path}: {e}")
            failed += 1
            continue
        file_bad = 0
        for i, r in enumerate(readings):
            errs = list(validator.iter_errors(r))
            total += 1
            if errs:
                file_bad += 1
                failed += 1
                print(f"FAIL {path} reading[{i}] ({r.get('sensor_id', '?')}):")
                for e in errs[:3]:
                    print(f"  - {e.json_path}: {e.message}")
        status = "FAIL" if file_bad else "OK"
        print(f"{status} {path}: {len(readings)} readings checked")
    print(f"\n{total - failed}/{total} readings valid")
    return 1 if failed else 0


def main():
    paths = sys.argv[1:] or sorted(glob.glob(os.path.join(ROOT, "examples", "*.json")))
    if not paths:
        print("no files to validate")
        return 2
    return validate_paths(paths)


if __name__ == "__main__":
    sys.exit(main())
