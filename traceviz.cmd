@echo off
setlocal
set ROOT=%~dp0
set PY=%ROOT%.vendor\python\python.exe
if exist "%PY%" goto run
set PY=python
:run
"%PY%" "%ROOT%tools\traceviz\serve.py" %*
