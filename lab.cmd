@echo off
if "%~1"=="" (
  echo Usage: lab.cmd ^<folder^> [pi-args]
  echo   .\lab.cmd my-run -a
  echo   .\lab.cmd F:\work\fnlab -a --empty-lab
  echo Relative names go under experiments\ inside this repo ^(gitignore^).
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\pi.ps1" --lab %*
