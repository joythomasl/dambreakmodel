@echo off
cd /d "%~dp0"
if exist ".runtime_tools\python-3.13.15\python.exe" (
  ".runtime_tools\python-3.13.15\python.exe" -m unittest discover -s tests -v
  exit /b
)
py -3 -m unittest discover -s tests -v
