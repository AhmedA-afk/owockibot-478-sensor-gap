"""USGS NWIS Water Services client (no API key required)."""

import math

import requests

SITE_SERVICE = "https://waterservices.usgs.gov/nwis/site/"
IV_SERVICE = "https://waterservices.usgs.gov/nwis/iv/"
TIMEOUT = 30

# USGS parameter codes mapped onto the #450 schema's allowed water_quality
# (parameter, unit) pairs.
PARAM_MAP = {
    "00010": ("temperature", "celsius"),
    "00300": ("dissolved_oxygen", "mg/L"),
    "00400": ("ph", "pH"),
    "63680": ("turbidity", "NTU"),
}


def bbox_for(lat, lon, radius_km):
    dlat = radius_km / 111.19
    dlon = radius_km / (111.19 * max(0.2, abs(math.cos(math.radians(lat)))))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def fetch_sites(lat, lon, radius_km):
    """Return stream-gage sites near a point via the NWIS site service (RDB)."""
    west, south, east, north = bbox_for(lat, lon, radius_km)
    params = {
        "format": "rdb",
        "bBox": f"{west:.4f},{south:.4f},{east:.4f},{north:.4f}",
        "siteType": "ST",
    }
    resp = requests.get(SITE_SERVICE, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return parse_sites_rdb(resp.text)


def parse_sites_rdb(text):
    """Parse NWIS site-service RDB text into site dicts."""
    sites = []
    data_started = False
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        if not line.strip():
            continue
        if not data_started:
            data_started = True  # header row
            continue
        if line.startswith("5s"):  # column-width row
            continue
        cols = line.split("\t")
        if len(cols) < 6:
            continue
        try:
            slat, slon = float(cols[4]), float(cols[5])
        except ValueError:
            continue
        alt = None
        if len(cols) > 8 and cols[8].strip():
            try:
                alt = float(cols[8])  # alt_va is in feet; converted below
            except ValueError:
                alt = None
        sites.append(
            {
                "id": cols[1].strip(),
                "sensor_id": f"USGS:{cols[1].strip()}",
                "name": cols[2].strip(),
                "lat": slat,
                "lon": slon,
                "elevation_m": round(alt * 0.3048, 2) if alt is not None else None,
                "source": "USGS NWIS Water Services",
            }
        )
    return sites


def fetch_latest_reading(site_no):
    """Return the latest real reading for a schema-supported parameter, or None.

    Queries instantaneous values for the last 7 days for the four USGS
    parameter codes that map onto the #450 schema.
    """
    params = {
        "format": "json",
        "sites": site_no,
        "parameterCd": ",".join(PARAM_MAP),
        "period": "P7D",
    }
    resp = requests.get(IV_SERVICE, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    try:
        payload = resp.json()
    except ValueError:
        return None
    best = None
    for ts in payload.get("value", {}).get("timeSeries", []):
        var_code = ts.get("variable", {}).get("variableCode", [{}])[0].get("value")
        if var_code not in PARAM_MAP:
            continue
        values = ts.get("values", [{}])[0].get("value", [])
        if not values:
            continue
        latest = values[-1]
        try:
            val = float(latest["value"])
        except (ValueError, TypeError, KeyError):
            continue
        parameter, unit = PARAM_MAP[var_code]
        ts_iso = latest.get("dateTime", "")
        if best is None or ts_iso > best["timestamp"]:
            best = {"parameter": parameter, "unit": unit, "value": val,
                    "timestamp": ts_iso, "usgs_code": var_code}
    return best
