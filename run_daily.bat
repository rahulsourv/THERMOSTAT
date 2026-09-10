@echo off
REM ThermoStats daily pipeline - launched by Windows Task Scheduler.
REM Uses absolute paths because Task Scheduler does not start in this folder.

cd /d "%~dp0"
"%~dp0ML\.venv\Scripts\python.exe" "%~dp0backend\pipeline.py"

REM Exit code 0 = success, 1 = failure. Task Scheduler shows this as
REM "Last Run Result", so a red 0x1 there means the run failed.
exit /b %ERRORLEVEL%
