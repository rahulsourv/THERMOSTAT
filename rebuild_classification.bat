@echo off
REM ---------------------------------------------------------------------------
REM SIH26162 stage 2: rebuild the event classification end to end.
REM
REM Run this once the OpenStreetMap fetch has finished. Every step is
REM resumable or idempotent, so it is safe to run again after an interruption:
REM   - fetch_osm_context skips batches it has already cached
REM   - the other steps simply recompute from scratch
REM
REM The daily pipeline (run_daily.bat) does NOT need this. It reuses the
REM already-trained classifier. Only re-run this when the OSM evidence or the
REM 2025 reference changes.
REM ---------------------------------------------------------------------------

cd /d "%~dp0"
set PY=%~dp0ML\.venv\Scripts\python.exe

echo(
echo [1/5] OpenStreetMap context (resumes from cache)
pushd ML
"%PY%" src\fetch_osm_context.py || (popd & exit /b 1)

echo(
echo [2/5] Build the event taxonomy
"%PY%" src\build_event_labels.py || (popd & exit /b 1)

echo(
echo [3/5] Train the stage-2 classifier
"%PY%" src\train_event_classifier.py || (popd & exit /b 1)

echo(
echo [4/5] Re-score tonight's detections with the new classes
"%PY%" src\create_hotspot_alerts.py || (popd & exit /b 1)
popd

echo(
echo [5/5] Load places and alerts into Supabase
"%PY%" backend\load_to_supabase.py || exit /b 1

echo(
echo Done. Reload the dashboard - the Classification page will show the new classes.
exit /b 0
