"""Gap geometry: haversine math, angular-sector gap detection, placement."""

import math

from .elevation import get_elevation

EARTH_KM = 6371.0


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def destination(lat, lon, bearing, distance_km):
    d = distance_km / EARTH_KM
    p1 = math.radians(lat)
    b = math.radians(bearing)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(b))
    l2 = math.radians(lon) + math.atan2(
        math.sin(b) * math.sin(d) * math.cos(p1),
        math.cos(d) - math.sin(p1) * math.sin(p2),
    )
    return math.degrees(p2), ((math.degrees(l2) + 540) % 360) - 180


def sector_gap(stations, n_sectors=12):
    """Find the largest angular sector run with no stations.

    Returns (start_bearing, end_bearing, mid_bearing, empty_sector_count,
    occupied_sectors).
    """
    width = 360.0 / n_sectors
    occupied = set()
    for s in stations:
        occupied.add(int(s["bearing"] // width) % n_sectors)
    if len(occupied) >= n_sectors:
        return (0.0, 0.0, 0.0, 0, sorted(occupied))
    # longest run of consecutive empty sectors (wrap-aware, doubled array)
    best_start, best_len = 0, 0
    cur_start, cur_len = None, 0
    for i in range(2 * n_sectors):
        if (i % n_sectors) in occupied:
            cur_start, cur_len = None, 0
        else:
            if cur_start is None:
                cur_start = i
            cur_len += 1
            if cur_len > best_len and cur_len <= n_sectors:
                best_start, best_len = cur_start, cur_len
    start = (best_start % n_sectors) * width
    end = start + best_len * width
    mid = (start + best_len * width / 2) % 360
    return (start % 360, end % 360, mid, best_len, sorted(occupied))


def recommend_placement(lat, lon, mid_bearing, radius_km, annotate_elev=True):
    """Pick a placement along the gap's mid bearing.

    Tries fractions of the search radius and keeps the highest-elevation
    candidate (elevation = upstream proxy). Returns (plat, plon, elev_m,
    rationale_lines).
    """
    fractions = [0.25, 0.5, 0.75, 1.0]
    cands = []
    for f in fractions:
        clat, clon = destination(lat, lon, mid_bearing, radius_km * f)
        elev = get_elevation(clat, clon) if annotate_elev else None
        cands.append({"lat": clat, "lon": clon, "elev_m": elev, "fraction": f})
    ranked = sorted(
        cands,
        key=lambda c: (c["elev_m"] is None, -(c["elev_m"] or 0), abs(c["fraction"] - 0.75)),
    )
    best = ranked[0]
    elev_note = (
        f"EPQS elevation {best['elev_m']:.1f} m"
        if best["elev_m"] is not None
        else "elevation lookup failed; placement by geometry only"
    )
    rationale = [
        f"Largest sensor gap lies along bearing {mid_bearing:.0f} deg "
        f"from the input river point.",
        f"Proposed station at {best['fraction']:.0%} of the {radius_km:.0f} km "
        f"search radius along that bearing; {elev_note}.",
        "Higher ground is treated as an upstream proxy (documented heuristic); "
        "true NHDPlus flowline tracing is out of scope for v0.1.",
    ]
    return best["lat"], best["lon"], best["elev_m"], rationale, cands
