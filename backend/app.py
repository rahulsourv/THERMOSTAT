"""
ThermoStats API.

Serves the model's alerts to a frontend. Every endpoint asks the database
for exactly the rows it needs - it never loads a CSV into memory.

Start it with:
    uvicorn backend.app:app --reload

Then open http://127.0.0.1:8000/docs to try the endpoints in your browser.
"""

import json
from pathlib import Path
from typing import Literal, Optional

import psycopg2
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .db import DatabaseUnavailable, get_cursor

app = FastAPI(
    title="ThermoStats API",
    description=(
        "Persistent thermal source alerts from NASA FIRMS satellite data, "
        "scored by a place-level model trained on 2025 behaviour."
    ),
    version="2.0.0",
)

# The frontend will run on a different port (e.g. 5173 for Vite), and
# browsers block that by default. This allows it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:3000", "http://127.0.0.1:3000",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)

@app.exception_handler(DatabaseUnavailable)
def database_unavailable(request: Request, exc: DatabaseUnavailable):
    """The database could not be reached - a 503, not a 500.

    Without this every endpoint answers a network blip with an unhandled
    exception and a full stack trace, which reads to a caller as "the API is
    broken" when the correct message is "try again shortly". 503 also tells
    proxies and clients that a retry is appropriate; 500 does not.
    """
    return JSONResponse(
        status_code=503,
        headers={"Retry-After": "10"},
        content={"error": "database_unavailable",
                 "detail": str(exc),
                 "hint": "The database is unreachable. This is usually "
                         "transient - retry in a few seconds."},
    )


@app.exception_handler(psycopg2.Error)
def database_error(request: Request, exc: psycopg2.Error):
    """A query failed. Report it without leaking a traceback to the client."""
    return JSONResponse(
        status_code=503,
        headers={"Retry-After": "10"},
        content={"error": "database_error",
                 "detail": f"{type(exc).__name__}: {exc}".strip()},
    )


AlertLevel = Literal["High", "Medium", "Low", "Natural (volcano)"]

# SIH26162 stage-2 taxonomy. "unclassified" covers detections at locations
# with no 2025 history, which cannot be typed from behaviour they never had.
EventClass = Literal[
    "gas_flare", "thermal_power_plant", "oil_refinery", "industrial_heat",
    "mining", "industrial_unspecified", "volcano", "agricultural_burning",
    "wildfire", "unknown", "unclassified",
]


def parse_bbox(bbox: Optional[str]):
    """Turn 'min_lon,min_lat,max_lon,max_lat' into four numbers.

    This is the rectangle the user is currently looking at on the map.
    """
    if not bbox:
        return None
    try:
        min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox.split(","))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="bbox must be 'min_lon,min_lat,max_lon,max_lat'",
        )
    if min_lat > max_lat or min_lon > max_lon:
        raise HTTPException(status_code=400, detail="bbox values are reversed")
    return min_lon, min_lat, max_lon, max_lat


@app.get("/")
def home():
    return {"message": "ThermoStats API is running", "docs": "/docs"}


@app.get("/api/model")
def model_metrics():
    """The model's report card - measured numbers, not marketing.

    Served from a file the training scripts produce, so the dashboard can
    never drift from what was actually measured.
    """
    path = (
        Path(__file__).resolve().parents[1]
        / "ML" / "models" / "model_metrics.json"
    )
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="model_metrics.json not found. Run train_hotspot_model.py.",
        )
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/health")
def health():
    """Is the API alive AND actually able to reach the database?

    Returns 200 with status "degraded" rather than raising, so a monitor can
    tell "the API process is up but the database is not" apart from "the API
    is down". Those need different responses and should not look alike.
    """
    try:
        with get_cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM alerts;")
            n = cur.fetchone()["n"]
        return {"status": "ok", "database": "connected", "alerts": n}
    except DatabaseUnavailable as exc:
        return {"status": "degraded", "database": "unreachable",
                "detail": str(exc)}
    except psycopg2.Error as exc:
        return {"status": "degraded", "database": "error",
                "detail": f"{type(exc).__name__}: {exc}".strip()}


@app.get("/api/summary")
def summary():
    """Dashboard tiles: how many alerts of each kind, and how many confirmed."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT alert_level,
                   count(*)                                AS count,
                   count(*) FILTER (WHERE near_power_plant) AS confirmed
            FROM alerts
            GROUP BY alert_level
            ORDER BY count DESC;
            """
        )
        by_level = cur.fetchall()

        cur.execute(
            """
            SELECT count(*)                                  AS total_alerts,
                   count(*) FILTER (WHERE known_place)       AS known_places,
                   count(*) FILTER (WHERE NOT known_place)   AS new_locations,
                   max(acq_date)                             AS latest_date
            FROM alerts;
            """
        )
        totals = cur.fetchone()

        cur.execute("SELECT count(*) AS n FROM places;")
        totals["places_in_reference"] = cur.fetchone()["n"]

    return {"totals": totals, "by_level": by_level}


@app.get("/api/alerts")
def get_alerts(
    level: Optional[AlertLevel] = Query(None, description="Filter by level"),
    bbox: Optional[str] = Query(
        None, description="Map rectangle: min_lon,min_lat,max_lon,max_lat"
    ),
    event_class: Optional[EventClass] = Query(
        None, description="Filter by classified thermal event type"
    ),
    min_score: float = Query(0, ge=0, le=100),
    confirmed_only: bool = Query(
        False, description="Only alerts near a known thermal power plant"
    ),
    limit: int = Query(100, ge=1, le=2000),
    offset: int = Query(0, ge=0),
):
    """The main alert list. Filters are combined with AND."""
    where, params = ["alert_score >= %s"], [min_score]

    if level:
        where.append("alert_level = %s")
        params.append(level)

    if event_class:
        where.append("event_class = %s")
        params.append(event_class)

    box = parse_bbox(bbox)
    if box:
        where.append(
            "longitude BETWEEN %s AND %s AND latitude BETWEEN %s AND %s"
        )
        params.extend([box[0], box[2], box[1], box[3]])

    if confirmed_only:
        where.append("near_power_plant")

    clause = " AND ".join(where)

    with get_cursor() as cur:
        cur.execute(f"SELECT count(*) AS n FROM alerts WHERE {clause};", params)
        total = cur.fetchone()["n"]

        cur.execute(
            f"""
            SELECT cell_id, latitude, longitude, acq_date, acq_time, frp,
                   confidence, daynight, static_probability, alert_score,
                   alert_level, why, known_place, is_volcanic, near_power_plant,
                   event_class, class_source, class_confidence
            FROM alerts
            WHERE {clause}
            ORDER BY alert_score DESC
            LIMIT %s OFFSET %s;
            """,
            params + [limit, offset],
        )
        rows = cur.fetchall()

    return {"total_matching": total, "returned": len(rows), "alerts": rows}


@app.get("/api/alerts/geojson")
def alerts_geojson(
    level: Optional[AlertLevel] = Query(None),
    event_class: Optional[EventClass] = Query(None),
    bbox: Optional[str] = Query(None),
    limit: int = Query(1000, ge=1, le=5000),
    one_per_place: bool = Query(
        True, description="Collapse repeat detections to one point per place"
    ),
):
    """Same data shaped as GeoJSON, which Leaflet can draw directly.

    one_per_place matters: a single flare can be detected 40 times in one
    night. Without this the map shows 40 markers for one factory.
    """
    where, params = ["true"], []

    if level:
        where.append("alert_level = %s")
        params.append(level)

    if event_class:
        where.append("event_class = %s")
        params.append(event_class)

    box = parse_bbox(bbox)
    if box:
        where.append(
            "longitude BETWEEN %s AND %s AND latitude BETWEEN %s AND %s"
        )
        params.extend([box[0], box[2], box[1], box[3]])

    clause = " AND ".join(where)

    # DISTINCT ON keeps the highest-scoring row per cell_id.
    selection = (
        "SELECT DISTINCT ON (cell_id) "
        if one_per_place
        else "SELECT "
    )
    inner_order = "ORDER BY cell_id, alert_score DESC" if one_per_place else ""

    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT * FROM (
                {selection}
                    cell_id, latitude, longitude, frp, acq_date,
                    static_probability, alert_score, alert_level, why,
                    is_volcanic, near_power_plant,
                    event_class, class_source, class_confidence
                FROM alerts
                WHERE {clause}
                {inner_order}
            ) t
            ORDER BY alert_score DESC
            LIMIT %s;
            """,
            params + [limit],
        )
        rows = cur.fetchall()

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    # GeoJSON is longitude first, then latitude.
                    "coordinates": [r["longitude"], r["latitude"]],
                },
                "properties": {
                    k: v for k, v in r.items()
                    if k not in ("latitude", "longitude")
                },
            }
            for r in rows
        ],
    }


@app.get("/api/classification")
def classification():
    """SIH26162 stage 2: the event-type breakdown and the model's report card.

    Returns the class mix twice over, because they answer different questions:
      by_class  - tonight's detections, what is burning right now
      places    - the 2025 reference, the standing catalogue of sources

    class_source is carried through deliberately. A type that came from
    OpenStreetMap or WRI is a mapped fact; one from the classifier is a
    prediction about a place nobody has mapped. The dashboard must never
    show them as the same kind of claim.
    """
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT event_class,
                   class_source,
                   count(*)                                 AS count,
                   count(DISTINCT cell_id)                  AS places,
                   round(avg(class_confidence)::numeric, 3) AS mean_confidence,
                   round(avg(alert_score)::numeric, 1)      AS mean_score,
                   count(*) FILTER (WHERE near_power_plant) AS confirmed
            FROM alerts
            WHERE event_class IS NOT NULL
            GROUP BY event_class, class_source
            ORDER BY count DESC;
            """
        )
        by_class = cur.fetchall()

        cur.execute(
            """
            SELECT event_class, count(*) AS places
            FROM places
            WHERE event_class IS NOT NULL
            GROUP BY event_class
            ORDER BY places DESC;
            """
        )
        reference = cur.fetchall()

        # Confidence spread over the places the model actually spoke about.
        # The dashboard draws this so the 90% publish gate is visibly a
        # measured decision rather than an arbitrary one.
        cur.execute(
            """
            SELECT width_bucket(class_confidence, 0, 1, 10) AS bucket,
                   count(*) AS places
            FROM places
            WHERE class_confidence IS NOT NULL
            GROUP BY bucket
            ORDER BY bucket;
            """
        )
        buckets = {int(r["bucket"]): int(r["places"]) for r in cur.fetchall()}

    confidence = [
        {"from": round(i / 10, 1), "to": round((i + 1) / 10, 1),
         "count": buckets.get(i + 1, 0)}
        for i in range(10)
    ]

    path = (
        Path(__file__).resolve().parents[1]
        / "ML" / "models" / "event_model_metrics.json"
    )
    metrics = (
        json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    )

    return {
        "by_class": by_class,
        "reference_places": reference,
        "confidence_histogram": confidence,
        "model": metrics,
        "trained": metrics is not None,
    }


# ---------------------------------------------------------------------------
# Vegetation fires - the OTHER side of the model.
#
# The model gives every place a static_probability. High means "persistent
# industrial-style source". LOW means the opposite: heat that is NOT tied to
# a fixed installation, which is what a crop fire or forest fire looks like.
#
# IMPORTANT: this is detection, not prediction. It tells you where something
# is burning right now, based on what the satellite already saw. It does not
# forecast where a fire will start - that needs weather, fuel dryness and
# vegetation data we do not have.
#
# Single detections are not useful on their own, because one fire covers
# many pixels. So nearby detections are grouped into fire EVENTS on a
# 0.1 degree grid (about 11 km), and ranked by total FRP - the sum of
# radiative power, which is a reasonable proxy for how big the fire is.
# ---------------------------------------------------------------------------

FIRE_GRID = 10          # 1/10 degree
MAX_STATIC_PROBABILITY = 0.2

FIRE_SELECT = f"""
    SELECT round(latitude  * {FIRE_GRID}) / {FIRE_GRID} AS latitude,
           round(longitude * {FIRE_GRID}) / {FIRE_GRID} AS longitude,
           count(*)                       AS detections,
           round(sum(frp)::numeric, 1)    AS total_frp,
           round(max(frp)::numeric, 1)    AS max_frp,
           round(avg(frp)::numeric, 1)    AS mean_frp,
           max(acq_date)                  AS latest_date,
           bool_or(known_place)           AS any_known_place,
           CASE WHEN sum(frp) >= 300 THEN 'Large'
                WHEN sum(frp) >=  50 THEN 'Moderate'
                ELSE 'Small' END          AS severity
    FROM alerts
    WHERE static_probability < {MAX_STATIC_PROBABILITY}
"""


def fire_query(bbox, min_frp, limit):
    where, params = [], []

    box = parse_bbox(bbox)
    if box:
        where.append(
            "longitude BETWEEN %s AND %s AND latitude BETWEEN %s AND %s"
        )
        params.extend([box[0], box[2], box[1], box[3]])

    extra = (" AND " + " AND ".join(where)) if where else ""

    sql = f"""
        SELECT * FROM (
            {FIRE_SELECT} {extra}
            GROUP BY 1, 2
        ) events
        WHERE total_frp >= %s
        ORDER BY total_frp DESC
        LIMIT %s;
    """
    return sql, params + [min_frp, limit]


def describe_fire(row):
    """Plain words, so the number is not the only thing on screen."""
    parts = [
        f"{row['detections']} detections clustered over ~11 km",
        f"peak intensity {row['max_frp']} FRP",
    ]
    if not row["any_known_place"]:
        parts.append("no persistent history here - looks like a new fire")
    else:
        parts.append("some repeat activity at this location")
    return ", ".join(parts)


@app.get("/api/fires")
def get_fires(
    bbox: Optional[str] = Query(None, description="min_lon,min_lat,max_lon,max_lat"),
    min_frp: float = Query(0, ge=0, description="minimum total FRP for the event"),
    limit: int = Query(100, ge=1, le=2000),
):
    """Active vegetation fires right now, grouped into fire events."""
    sql, params = fire_query(bbox, min_frp, limit)

    with get_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

        cur.execute(
            f"""
            SELECT count(*) AS events, sum(detections) AS detections,
                   count(*) FILTER (WHERE severity = 'Large')    AS large,
                   count(*) FILTER (WHERE severity = 'Moderate') AS moderate,
                   count(*) FILTER (WHERE severity = 'Small')    AS small
            FROM ({FIRE_SELECT} GROUP BY 1, 2) e;
            """
        )
        totals = cur.fetchone()

    for r in rows:
        r["why"] = describe_fire(r)

    return {"totals": totals, "returned": len(rows), "fires": rows}


@app.get("/api/fires/geojson")
def fires_geojson(
    bbox: Optional[str] = Query(None),
    min_frp: float = Query(0, ge=0),
    limit: int = Query(1500, ge=1, le=5000),
):
    """Same fire events, shaped for Leaflet."""
    sql, params = fire_query(bbox, min_frp, limit)

    with get_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(r["longitude"]), float(r["latitude"])],
                },
                "properties": {
                    **{k: v for k, v in r.items()
                       if k not in ("latitude", "longitude")},
                    "why": describe_fire(r),
                },
            }
            for r in rows
        ],
    }


@app.get("/api/runs")
def get_runs(limit: int = Query(20, ge=1, le=200)):
    """History of the automated pipeline - did last night's run work?

    Check this first when the data looks stale. A 'failed' row with an
    error message is much faster to read than a log file.
    """
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, started_at, finished_at, status, detections,
                   high_alerts, error,
                   round(extract(epoch FROM finished_at - started_at)) AS seconds
            FROM pipeline_runs
            ORDER BY started_at DESC
            LIMIT %s;
            """,
            [limit],
        )
        runs = cur.fetchall()

        cur.execute(
            """
            SELECT count(*) FILTER (WHERE status = 'success') AS successes,
                   count(*) FILTER (WHERE status = 'failed')  AS failures,
                   max(started_at) FILTER (WHERE status = 'success')
                       AS last_success
            FROM pipeline_runs;
            """
        )
        stats = cur.fetchone()

    return {"summary": stats, "runs": runs}


@app.get("/api/metrics")
def metrics():
    """Every measured result the models produced, in one call.

    Served straight from the JSON files the training scripts write, so the
    Model Report page can never drift from what was actually measured - there
    is no number here that a person typed in.

    Any file that has not been produced yet comes back as null rather than an
    error, so the page can show what exists and say what is missing.
    """
    base = Path(__file__).resolve().parents[1] / "ML" / "models"

    def load(name):
        path = base / name
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    return {
        "stage1_production": load("model_metrics.json"),
        "stage1_m2": load("stage1_m2_baseline_spec.json"),
        "stage1_m2_confusion": load("stage1_m2_confusion.json"),
        "stage2": load("event_model_metrics.json"),
        "dbscan": load("dbscan_metrics.json"),
    }


@app.get("/api/places/{cell_id}")
def get_place(cell_id: int):
    """Drill-down: everything we know about one 5 km place."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM places WHERE cell_id = %s;", [cell_id])
        place = cur.fetchone()

        if not place:
            raise HTTPException(
                status_code=404, detail=f"No place with cell_id {cell_id}"
            )

        cur.execute(
            """
            SELECT acq_date, acq_time, frp, confidence, daynight,
                   alert_score, alert_level
            FROM alerts
            WHERE cell_id = %s
            ORDER BY alert_score DESC
            LIMIT 50;
            """,
            [cell_id],
        )
        place["recent_detections"] = cur.fetchall()

    # Say plainly what this place is and is not, so the frontend does not
    # have to invent the wording.
    if place["is_volcanic"]:
        place["verdict"] = (
            f"Natural - volcano {place['km_to_volcano']:.1f} km away"
        )
    elif place["near_power_plant"]:
        place["verdict"] = (
            "Confirmed - known thermal power plant "
            f"{place['km_to_thermal_plant']:.1f} km away"
        )
    else:
        place["verdict"] = (
            "Unconfirmed persistent source. No power plant or volcano nearby "
            "in our reference data - could be a gas flare, kiln or furnace "
            "we have no record of."
        )

    return place
