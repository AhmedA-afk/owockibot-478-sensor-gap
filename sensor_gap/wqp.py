"""EPA Water Quality Portal station search client (no API key required).

NOTE: the WQP station search endpoint is documented to support
``mimeType=json``, but as of 2026-09-30 the server answers 406 Not Acceptable
for that mime type. ``mimeType=csv`` works, so this client requests CSV and
parses it. The exact endpoint used is recorded in the README.
"""

import csv
import io

import requests

STATION_SEARCH = "https://www.waterqualitydata.us/data/Station/search"
TIMEOUT = 60
HEADERS = {"User-Agent": "sensor-gap/0.1 (owockibot bounty #478)"}


def fetch_stations(lat, lon, radius_km, max_stations=400):
    """Return monitoring stations near a point via WQP station search (CSV)."""
    within_deg = radius_km / 111.19
    params = {
        "mimeType": "csv",
        "lat": f"{lat:.4f}",
        "long": f"{lon:.4f}",
        "within": f"{within_deg:.4f}",
    }
    resp = requests.get(STATION_SEARCH, params=params, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return parse_stations_csv(resp.text, max_stations=max_stations)


def parse_stations_csv(text, max_stations=400):
    """Parse WQP station-search CSV text into station dicts."""
    reader = csv.DictReader(io.StringIO(text))
    stations = []
    for row in reader:
        try:
            slat = float(row["LatitudeMeasure"])
            slon = float(row["LongitudeMeasure"])
        except (ValueError, TypeError, KeyError):
            continue
        mlid = row.get("MonitoringLocationIdentifier", "").strip()
        org = row.get("OrganizationIdentifier", "").strip()
        stations.append(
            {
                "id": f"WQP:{mlid}" if mlid else f"WQP:{org}:{slat:.4f},{slon:.4f}",
                "sensor_id": f"WQP:{mlid}" if mlid else f"WQP:{org}:{slat:.4f},{slon:.4f}",
                "name": row.get("MonitoringLocationName", "").strip() or mlid,
                "lat": slat,
                "lon": slon,
                "type": row.get("MonitoringLocationTypeName", "").strip(),
                "org": row.get("OrganizationFormalName", "").strip() or org,
                "huc8": row.get("HUCEightDigitCode", "").strip(),
                "elevation_m": None,
                "source": "EPA Water Quality Portal",
            }
        )
        if len(stations) >= max_stations:
            break
    return stations
