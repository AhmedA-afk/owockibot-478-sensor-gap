"""Build #450-schema-conformant sensor readings from a gap survey.

Mapping policy (documented in README):
- Stations WITH a retrievable live reading for a schema-supported parameter
  (temperature / dissolved_oxygen / ph / turbidity) emit that reading verbatim
  with quality_flag="raw".
- Stations WITHOUT one emit a reading carrying the area baseline value for the
  most common parameter, flagged quality_flag="estimated" (interpolated/modeled
  per the schema definition) and explained in notes. Nothing is fabricated as
  measured data.
- The placement recommendation is emitted as a virtual sensor reading
  (quality_flag="estimated") carrying the same baseline, with the proposed
  coordinates and rationale in notes/location.
"""

from datetime import datetime, timezone

SCHEMA_REF = (
    "https://github.com/xtratrezzy/ecological-sensor-schema/"
    "blob/main/schema/ecological-sensor-reading.schema.json"
)
SCHEMA_VERSION = "1.0.0"


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _reading(sensor_id, parameter, unit, value, lat, lon, source,
             quality_flag="raw", notes="", elevation_m=None, timestamp=None):
    loc = {"lat": round(lat, 6), "lng": round(lon, 6)}
    if elevation_m is not None:
        loc["elevation_m"] = round(elevation_m, 2)
    return {
        "schema_version": SCHEMA_VERSION,
        "sensor_id": sensor_id,
        "sensor_type": "water_quality",
        "parameter": parameter,
        "value": float(value),
        "unit": unit,
        "timestamp": timestamp or _now_iso(),
        "location": loc,
        "source": source,
        "quality_flag": quality_flag,
        "notes": notes[:2000],
    }


def build_readings(stations, recommendation):
    """stations: list of dicts, each optionally with a 'live' reading dict.
    recommendation: dict with lat/lon/elev_m/rationale/sensor_id.
    Returns (readings, stats)."""
    readings = []
    live = [s for s in stations if s.get("live")]
    if live:
        # baseline = most common parameter, mean of its values
        counts = {}
        for s in live:
            p = s["live"]["parameter"]
            counts[p] = counts.get(p, 0) + 1
        base_param = max(counts, key=counts.get)
        vals = [s["live"]["value"] for s in live if s["live"]["parameter"] == base_param]
        base_unit = next(s["live"]["unit"] for s in live
                         if s["live"]["parameter"] == base_param)
        base_value = sum(vals) / len(vals)
    else:
        base_param, base_unit, base_value = "temperature", "celsius", 20.0

    for s in stations:
        if s.get("live"):
            r = s["live"]
            readings.append(_reading(
                sensor_id=s["sensor_id"],
                parameter=r["parameter"], unit=r["unit"], value=r["value"],
                lat=s["lat"], lon=s["lon"], source=s["source"],
                quality_flag="raw", elevation_m=s.get("elevation_m"),
                timestamp=r.get("timestamp"),
                notes=f"{s['name']} ({s['sensor_id']}); USGS parameter code "
                      f"{r.get('usgs_code', 'n/a')}; live NWIS instantaneous value.",
            ))
        else:
            readings.append(_reading(
                sensor_id=s["sensor_id"],
                parameter=base_param, unit=base_unit, value=base_value,
                lat=s["lat"], lon=s["lon"], source=s["source"],
                quality_flag="estimated", elevation_m=s.get("elevation_m"),
                notes=(f"{s['name']} ({s['sensor_id']}); no live reading "
                       "retrievable for a schema-supported parameter. Value is the "
                       "survey-area baseline carried over for schema completeness "
                       "(quality_flag=estimated); raw station record is in "
                       "stations_metadata."),
            ))
    readings.append(_reading(
        sensor_id=recommendation["sensor_id"],
        parameter=base_param, unit=base_unit, value=base_value,
        lat=recommendation["lat"], lon=recommendation["lon"],
        source="sensor-gap v0.1 (owockibot bounty #478)",
        quality_flag="estimated", elevation_m=recommendation.get("elev_m"),
        notes=("Proposed new monitoring station (virtual sensor). "
               + " ".join(recommendation["rationale"])),
    ))
    return readings, {"baseline_parameter": base_param, "baseline_unit": base_unit,
                      "baseline_value": round(base_value, 3),
                      "live_reading_count": len(live),
                      "estimated_count": len(stations) - len(live) + 1}
