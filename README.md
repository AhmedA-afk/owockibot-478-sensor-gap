# sensor-gap — Sensor Gap Finder

CLI tool for **owockibot bounty #478**: given a river point (lat/lon), find the
nearest upstream sensor gap and suggest an optimal placement for a new
monitoring station, using **USGS NWIS** and **EPA Water Quality Portal** data.

## What it does

1. Queries USGS NWIS (stream-gage site service) and the EPA Water Quality
   Portal (station search) for monitoring stations within a configurable
   radius (default 25 km) of the input river point.
2. Detects the largest sensor gap: the input point is divided into angular
   sectors (default 12 x 30 deg) and the longest run of empty sectors wins.
3. Estimates "upstream-ness" with a documented elevation heuristic (see below).
4. Emits a human-readable CLI summary plus a JSON report whose every
   sensor/station record conforms to the **#450 ecological sensor JSON schema**
   (`schema/ecological-sensor-reading.schema.json`,
   schema_version `1.0.0`).

## Data sources (exact endpoints)

No API keys needed. All endpoints are public and free.

| Source | Endpoint used |
|---|---|
| USGS NWIS site service | `https://waterservices.usgs.gov/nwis/site/?format=rdb&bBox=<w>,<s>,<e>,<n>&siteType=ST` |
| USGS NWIS instantaneous values | `https://waterservices.usgs.gov/nwis/iv/?format=json&sites=<id>&parameterCd=00010,00300,00400,63680&period=P7D` |
| EPA WQP station search | `https://www.waterqualitydata.us/data/Station/search?mimeType=csv&lat=<lat>&long=<lon>&within=<deg>` |
| USGS Elevation Point Query Service | `https://epqs.nationalmap.gov/v1/json?x=<lon>&y=<lat>&units=Meters` |

Note: the WQP station search is documented to support `mimeType=json`, but as
of 2026-09-30 the server returns `406 Not Acceptable` for it. `mimeType=csv`
works, so this tool requests CSV and parses it. The README records the exact
working endpoint.

USGS parameter codes are mapped onto the #450 schema's allowed
water_quality (parameter, unit) pairs: `00010` -> (temperature, celsius),
`00300` -> (dissolved_oxygen, mg/L), `00400` -> (ph, pH),
`63680` -> (turbidity, NTU).

## Upstream heuristic and its limitations

True river-network tracing (NHDPlus flowlines) is **out of scope for v0.1**.
Instead, candidate placements along the gap's mid bearing are sampled at
25/50/75/100% of the search radius and ranked by ground elevation from the
USGS EPQS: higher ground is treated as a **weak upstream proxy**. Honest
limitations:

- On flat coastal plains (e.g. Louisiana, where gradients are a few meters
  over tens of km) the heuristic is weak; geometry dominates.
- Tributary vs mainstem topology is not resolved.
- Elevation comes from a coarse national DEM, not the river thalweg.

The JSON report's `upstream_heuristic` block states this plainly, and the
`recommendation.rationale` repeats it.

## #450 schema conformance

Every record in the report's `readings` array (and in `examples/*.json`)
validates against
`schema/ecological-sensor-reading.schema.json` (the #450 winning schema,
schema_version `1.0.0`) with `additionalProperties: false` enforced.

Mapping policy:

- Stations with a retrievable **live** reading for a schema-supported
  parameter emit that reading verbatim (`quality_flag: "raw"`).
- Stations without one emit a reading carrying the survey-area baseline value
  for the most common parameter, flagged `quality_flag: "estimated"`
  (interpolated/modeled per the schema) and explained in `notes`. Nothing is
  fabricated as measured data; raw station metadata lives in
  `stations_metadata`.
- The placement recommendation is emitted as a **virtual sensor** reading
  (`sensor_id: VIRTUAL:sensor-gap-478:<hash>`, `quality_flag: "estimated"`)
  with the proposed coordinates (plus `elevation_m`) and the rationale in
  `notes`.

Validate any output with:

```
python scripts/validate.py [path ...]   # defaults to examples/*.json
python -m unittest discover -s tests
```

## Installation

```
pip install -r requirements.txt
pip install -e .        # provides the `sensor-gap` console script
```

Dependencies: `requests`, `jsonschema` only.

## CLI usage

```
sensor-gap --lat 30.4457 --lon -91.1916 --radius-km 25 --out report.json
```

Options: `--radius-km` (default 25), `--sectors` (default 12),
`--max-readings` (cap on live USGS reading fetches, default 12),
`--no-live` (use the bundled Baton Rouge sample captures instead of live
APIs), `--no-elevation` (skip EPQS lookups), `--out` (default
`sensor_gap_report.json`).

### Real example (Mississippi River at Baton Rouge, USGS gage 07374000)

```
$ sensor-gap --lat 30.4457 --lon -91.1916 --radius-km 25 --out report.json
sensor-gap v0.1.0 [live mode]
River point: 30.4457, -91.1916  radius: 25 km
Stations: 161  (USGS NWIS: 159, EPA WQP: 2)
Nearest station: 0.01 km away
Largest gap: 1/12 empty sectors, mid bearing 315 deg
Recommended placement: 30.525157, -91.283879  (elev 13.0 m)
  - Largest sensor gap lies along bearing 315 deg from the input river point.
  - Proposed station at 50% of the 25 km search radius along that bearing; EPQS elevation 13.0 m.
  - Higher ground is treated as an upstream proxy (documented heuristic); true NHDPlus flowline tracing is out of scope for v0.1.
Readings in report: 162 (1 live, 161 estimated)
Report written: report.json
```

Sample output: `examples/baton-rouge-sample-run.json` (a real run, 162
readings, all schema-valid).

## Repository layout

```
sensor-gap/
  LICENSE            MIT
  README.md
  requirements.txt   requests, jsonschema
  pyproject.toml     provides the `sensor-gap` console script
  sensor_gap/        CLI package (cli.py, usgs.py, wqp.py, elevation.py, gaps.py, schema_report.py)
  schema/            #450 ecological-sensor-reading.schema.json (schema_version 1.0.0)
  scripts/validate.py
  examples/          baton-rouge-sample-run.json (real run), multi-reading-example.json,
                     placement-recommendation.json
  tests/             schema-conformance tests (jsonschema)
  data/samples/      bundled real API captures for --no-live mode
```

## Failure handling

Each API call is wrapped: if USGS or WQP fails, the tool reports a clear
error (and exits non-zero if nothing was retrieved); if EPQS fails, placement
falls back to geometry with an honest note. `--no-live` runs fully offline on
the bundled sample captures in `data/samples/`.
