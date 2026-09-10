"""
The daily ThermoStats pipeline.

    download fresh FIRMS  ->  score against 2025 place history  ->  Supabase

Run it by hand:
    python backend/pipeline.py

Or let Windows Task Scheduler run run_daily.bat once a day.

Design rules for something that runs unattended:

  * Every step either succeeds or stops the run. A half-finished pipeline
    must never leave the API serving broken data.
  * Nothing is deleted until the replacement is ready. The database load is
    one transaction, so a failure rolls back and last night's alerts stay up.
  * Every run is written to the pipeline_runs table, success or failure, so
    you can see what happened without reading log files.
"""

import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.settings import connection_kwargs, describe

ROOT = Path(__file__).resolve().parents[1]
ML_DIR = ROOT / "ML"
PYTHON = ML_DIR / ".venv" / "Scripts" / "python.exe"
LOG_DIR = ROOT / "logs"

STEP_TIMEOUT_SECONDS = 1800     # 30 minutes; the model scoring is the slow part


def log(message, logfile):
    stamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {message}"
    print(line, flush=True)
    logfile.write(line + "\n")
    logfile.flush()


def run_step(name, args, cwd, logfile):
    """Run one script. Raises if it fails, which aborts the whole pipeline."""
    log(f"START  {name}", logfile)
    started = time.time()

    result = subprocess.run(
        [str(PYTHON)] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=STEP_TIMEOUT_SECONDS,
    )

    for line in result.stdout.splitlines():
        logfile.write(f"        | {line}\n")

    if result.returncode != 0:
        for line in result.stderr.splitlines()[-25:]:
            log(f"        ! {line}", logfile)
        raise RuntimeError(f"{name} failed with exit code {result.returncode}")

    log(f"DONE   {name}  ({time.time() - started:.0f}s)", logfile)
    return result.stdout


def record_run(status, detections, high_alerts, error, started_at):
    """Write the outcome to the database so it is visible from the API."""
    try:
        with psycopg2.connect(**connection_kwargs()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pipeline_runs
                        (started_at, finished_at, status, detections,
                         high_alerts, error)
                    VALUES (%s, %s, %s, %s, %s, %s);
                    """,
                    (started_at, datetime.now(timezone.utc), status,
                     detections, high_alerts, error),
                )
    except Exception as exc:
        # Never let logging failure hide the real result.
        print(f"WARNING: could not record run: {exc}", file=sys.stderr)


def main():
    LOG_DIR.mkdir(exist_ok=True)
    started_at = datetime.now(timezone.utc)
    logfile_path = LOG_DIR / f"pipeline_{started_at:%Y%m%d_%H%M%S}.log"

    detections = high_alerts = None
    status, error = "success", None

    with logfile_path.open("w", encoding="utf-8") as logfile:
        log("=" * 62, logfile)
        log("ThermoStats daily pipeline", logfile)
        log(f"database: {describe()}", logfile)
        log("=" * 62, logfile)

        try:
            # 1. Fresh satellite data. Refuses to save a suspiciously
            #    small response, so a bad day cannot poison the pipeline.
            out = run_step(
                "download FIRMS",
                ["src/download_firms.py"], ML_DIR, logfile,
            )
            for line in out.splitlines():
                if line.startswith("Detections downloaded:"):
                    detections = int(line.split(":")[1].strip().replace(",", ""))

            # 2. Score those detections against what each place did in 2025.
            out = run_step(
                "score alerts",
                ["src/create_hotspot_alerts.py"], ML_DIR, logfile,
            )
            for line in out.splitlines():
                if line.strip().startswith("High "):
                    high_alerts = int(line.split()[-1].replace(",", ""))

            # 3. Push only the alerts. Places change yearly, not daily.
            run_step(
                "load to Supabase",
                ["backend/load_to_supabase.py", "--alerts-only"],
                ROOT, logfile,
            )

            # 4. Refresh the map file.
            run_step(
                "rebuild map",
                ["src/create_hotspot_alert_map.py"], ML_DIR, logfile,
            )

            log("", logfile)
            log(f"PIPELINE OK - {detections:,} detections, "
                f"{high_alerts:,} High alerts", logfile)

        except Exception as exc:
            status = "failed"
            error = f"{type(exc).__name__}: {exc}"
            log("", logfile)
            log(f"PIPELINE FAILED - {error}", logfile)
            logfile.write(traceback.format_exc())

    record_run(status, detections, high_alerts, error, started_at)
    print(f"\nLog written to: {logfile_path}")
    return 0 if status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
