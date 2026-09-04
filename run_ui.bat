@echo off
REM Launcher for ECOWHISPER Futuristic Web Command Center
set PY=C:\Users\KAIRAV\AppData\Local\Programs\Python\Python311\python.exe
if not exist "%PY%" set PY=python
"%PY%" "%~dp0main.py" --ui %*
