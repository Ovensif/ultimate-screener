@echo off
REM Run from ultimate-screener project root. Optionally activate venv first.
cd /d "%~dp0.."
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
python src\main.py %*
