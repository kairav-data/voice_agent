@echo off
REM Launcher - uses the Python 3.11 install that has the dependencies.
set PY=C:\Users\KAIRAV\AppData\Local\Programs\Python\Python311\python.exe
if not exist "%PY%" set PY=python
"%PY%" "%~dp0main.py" %*
