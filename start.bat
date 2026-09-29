@echo off
cd /d "%~dp0"
if exist ".runtime_tools\python-3.13.15\python.exe" (
  ".runtime_tools\python-3.13.15\python.exe" run.py
  exit /b
)
py -3 run.py
