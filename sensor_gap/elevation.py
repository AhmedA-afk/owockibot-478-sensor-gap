"""USGS Elevation Point Query Service client (no API key required).

Used ONLY as a heuristic proxy for upstream-ness: in the absence of true
NHDPlus flowline tracing (out of scope for v0.1), higher ground elevation is
treated as a weak upstream indicator. See README limitations.
"""

import requests

EPQS = "https://epqs.nationalmap.gov/v1/json"
TIMEOUT = 60

_cache = {}


def get_elevation(lat, lon):
    """Return ground elevation in meters, or None on failure."""
    key = (round(lat, 4), round(lon, 4))
    if key in _cache:
        return _cache[key]
    try:
        resp = requests.get(
            EPQS,
            params={"x": lon, "y": lat, "units": "Meters"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        val = float(resp.json()["value"])
        _cache[key] = val
        return val
    except Exception:
        _cache[key] = None
        return None
