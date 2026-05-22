@echo off
setlocal
cd /d "%~dp0"

if exist "WF1_KR_Steam_Patch_GUI.exe" (
  start "" "%~dp0WF1_KR_Steam_Patch_GUI.exe" %*
  exit /b 0
)

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 tooling\wfantasy_steam_kr_patch_gui.py
) else (
  where python >nul 2>nul
  if %ERRORLEVEL%==0 (
    python tooling\wfantasy_steam_kr_patch_gui.py
  ) else (
    echo WF1_KR_Steam_Patch_GUI.exe not found.
    echo Use the packaged release that includes the local Python runtime, or rebuild it with:
    echo python tooling\build_ddraw_proxy.py
    echo python -m PyInstaller --noconsole --onefile --name WF1_KR_Steam_Patch_GUI --paths tooling tooling\wfantasy_steam_kr_patch_gui.py
    pause
    exit /b 1
  )
)

if errorlevel 1 pause
