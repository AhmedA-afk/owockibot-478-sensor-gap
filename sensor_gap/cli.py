"""sensor-gap CLI: find the nearest upstream sensor gap for a river point."""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import requests

from . import usgs, wqp, gaps, elevation, schema_report

VERSION = "0.1.0"
SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "samples")


def load_sample(lat, lon, radius_km):
    """Offline sample mode: parse bundled real API captures from Baton Rouge."""
    with open(os.path.join(SAMPLE_DIR, "usgs-sites.rdb"), encoding="utf-8") as f:
        usgs_sites = usgs.parse_sites_rdb(f.read())
    with open(os.path.join(SAMPLE_DIR, "wqp-stations.csv"), encoding="utf-8") as f:
        wqp_stations = wqp.parse_stations_csv(f.read())
    # keep only stations within the requested radius of the requested point
    kept = []
    for s in usgs_sites + wqp_stations:
        d = gaps.haversine_km(lat, lon, s["lat"], s["lon"])
        if d <= radius_km:
            s = dict(s)
            s["distance_km"] = d
            kept.append(s)
    return kept, True


def fetch_live(lat, lon, radius_km, max_readings):
    stations = []
    errors = []
    try:
        for s in usgs.fetch_sites(lat, lon, radius_km):
            s["distance_km"] = gaps.haversine_km(lat, lon, s["lat"], s["lon"])
            stations.append(s)
    except Exception as e:  # noqa: BLE001
        errors.append(f"USGS NWIS site service failed: {e}")
    try:
        for s in wqp.fetch_stations(lat, lon, radius_km):
            s["distance_km"] = gaps.haversine_km(lat, lon, s["lat"], s["lon"])
            stations.append(s)
    except Exception as e:  # noqa: BLE001
        errors.append(f"EPA WQP station search failed: {e}")
    if not stations:
        raise RuntimeError("No stations retrieved. " + " ".join(errors))

    # keep only stations inside the circular search radius, then dedupe:
    # WQP mirrors many USGS sites; drop near-duplicates (<150 m),
    # preferring the USGS record (it carries elevation + live readings).
    in_radius = [s for s in stations if s["distance_km"] <= radius_km]
    deduped = []
    for s in sorted(in_radius, key=lambda x: (0 if x["source"].startswith("USGS") else 1,
                                            x["distance_km"])):
        if any(gaps.haversine_km(s["lat"], s["lon"], k["lat"], k["lon"]) < 0.15
               for k in deduped):
            continue
        deduped.append(s)

    # live instantaneous readings for the nearest USGS sites (bounded).
    fetched = 0
    for s in sorted(deduped, key=lambda x: x["distance_km"]):
        if fetched >= max_readings:
            break
        if not s["source"].startswith("USGS"):
            continue
        try:
            live = usgs.fetch_latest_reading(s["id"])
        except Exception:  # noqa: BLE001
            live = None
        if live:
            s["live"] = live
            fetched += 1
    return deduped, errors


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="sensor-gap",
        description="Find the nearest upstream sensor gap for a river point "
                    "using USGS NWIS + EPA WQP data.",
    )
    ap.add_argument("--lat", type=float, required=True, help="River point latitude")
    ap.add_argument("--lon", type=float, required=True, help="River point longitude")
    ap.add_argument("--radius-km", type=float, default=25.0,
                    help="Search radius in km (default 25)")
    ap.add_argument("--sectors", type=int, default=12,
                    help="Angular sectors for gap detection (default 12)")
    ap.add_argument("--out", default="sensor_gap_report.json",
                    help="JSON report output path")
    ap.add_argument("--no-live", action="store_true",
                    help="Use bundled sample data instead of live APIs")
    ap.add_argument("--max-readings", type=int, default=12,
                    help="Max USGS stations to fetch live readings for")
    ap.add_argument("--no-elevation", action="store_true",
                    help="Skip EPQS elevation lookups")
    args = ap.parse_args(argv)

    if args.no_live:
        stations, _ = load_sample(args.lat, args.lon, args.radius_km)
        mode, errors = "sample", []
        for s in stations:
            s["bearing"] = gaps.bearing_deg(args.lat, args.lon, s["lat"], s["lon"])
    else:
        try:
            stations, errors = fetch_live(args.lat, args.lon, args.radius_km,
                                          args.max_readings)
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        mode = "live"
        for s in stations:
            s["bearing"] = gaps.bearing_deg(args.lat, args.lon, s["lat"], s["lon"])

    start_b, end_b, mid_b, empty_n, occupied = gaps.sector_gap(stations, args.sectors)
    plat, plon, pelev, rationale, _cands = gaps.recommend_placement(
        args.lat, args.lon, mid_b, args.radius_km, annotate_elev=not args.no_elevation)
    rec_id = ("VIRTUAL:sensor-gap-478:"
              + hashlib.sha1(f"{plat:.4f},{plon:.4f}".encode()).hexdigest()[:8])
    recommendation = {"sensor_id": rec_id, "lat": plat, "lon": plon,
                      "elev_m": pelev, "rationale": rationale}

    readings, rstats = schema_report.build_readings(stations, recommendation)
    nearest = min((s["distance_km"] for s in stations), default=None)

    report = {
        "tool": f"sensor-gap {VERSION} (owockibot bounty #478)",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": mode,
        "schema_ref": schema_report.SCHEMA_REF,
        "input": {"lat": args.lat, "lon": args.lon, "radius_km": args.radius_km,
                  "sectors": args.sectors},
        "sources": {
            "usgs_nwis_site": "https://waterservices.usgs.gov/nwis/site/?format=rdb"
                              "&bBox=<w>,<s>,<e>,<n>&siteType=ST",
            "usgs_nwis_iv": "https://waterservices.usgs.gov/nwis/iv/?format=json"
                            "&sites=<id>&parameterCd=00010,00300,00400,63680&period=P7D",
            "epa_wqp_station": "https://www.waterqualitydata.us/data/Station/search"
                               "?mimeType=csv&lat=<lat>&long=<lon>&within=<deg>",
            "usgs_epqs": "https://epqs.nationalmap.gov/v1/json"
                         "?x=<lon>&y=<lat>&units=Meters",
        },
        "upstream_heuristic": {
            "method": "elevation proxy via USGS EPQS",
            "description": "Candidate placements along the gap bearing are ranked "
                           "by ground elevation; higher ground is treated as a "
                           "weak upstream indicator.",
            "limitations": "True NHDPlus flowline tracing is out of scope for "
                           "v0.1. Elevation is only a proxy: on flat coastal "
                           "plains (e.g. Louisiana) gradients are tiny and the "
                           "heuristic is weak; tributary vs mainstem topology is "
                           "not resolved.",
        },
        "gap_analysis": {
            "stations_found": len(stations),
            "nearest_station_km": round(nearest, 2) if nearest is not None else None,
            "empty_sectors": empty_n,
            "sector_span_deg": [round(start_b, 1), round(end_b, 1)],
            "gap_mid_bearing_deg": round(mid_b, 1),
            "occupied_sectors": occupied,
        },
        "recommendation": {
            "lat": round(plat, 6), "lon": round(plon, 6),
            "elevation_m": round(pelev, 2) if pelev is not None else None,
            "rationale": rationale,
            "virtual_sensor_id": rec_id,
        },
        "reading_stats": rstats,
        "readings": readings,
        "stations_metadata": [
            {k: s.get(k) for k in ("sensor_id", "name", "lat", "lon",
                                  "distance_km", "bearing", "elevation_m",
                                  "source", "type", "org", "huc8")}
            for s in stations
        ],
        "errors": errors,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    # human-readable summary
    usgs_n = sum(1 for s in stations if s["source"].startswith("USGS"))
    wqp_n = len(stations) - usgs_n
    print(f"sensor-gap v{VERSION} [{mode} mode]")
    print(f"River point: {args.lat:.4f}, {args.lon:.4f}  radius: {args.radius_km:g} km")
    print(f"Stations: {len(stations)}  (USGS NWIS: {usgs_n}, EPA WQP: {wqp_n})")
    if nearest is not None:
        print(f"Nearest station: {nearest:.2f} km away")
    print(f"Largest gap: {empty_n}/{args.sectors} empty sectors, "
          f"mid bearing {mid_b:.0f} deg")
    print(f"Recommended placement: {plat:.6f}, {plon:.6f}"
          + (f"  (elev {pelev:.1f} m)" if pelev is not None else ""))
    for line in rationale:
        print(f"  - {line}")
    print(f"Readings in report: {len(readings)} "
          f"({rstats['live_reading_count']} live, {rstats['estimated_count']} estimated)")
    print(f"Report written: {args.out}")
    for e in errors:
        print(f"WARNING: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
