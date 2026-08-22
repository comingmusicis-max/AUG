@echo off
setlocal
title JJ - grade

rem Repo root, from jobs\jj\color\
set ROOT=%~dp0..\..\..
set SKILL=%ROOT%\.claude\skills\davinci-color

set PY=python
where py >nul 2>&1
if %errorlevel%==0 set PY=py -3

echo ============================================
echo  JJ - golden hour grade
echo ============================================
echo.

echo [1/5] checking the connection to Resolve...
%PY% "%SKILL%\scripts\doctor.py"
if %errorlevel% neq 0 (
  echo.
  echo Stopped. Fix what the doctor listed above, then run this again.
  pause
  exit /b 1
)
echo.

echo [2/5] building the LUTs...
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo.
  echo   This needs to run as Administrator. Resolve's LUT folder sits in
  echo   ProgramData, and without it the LUT lands somewhere Resolve does not
  echo   read - the grade would fail halfway through instead of now.
  echo.
  echo   Close this, right-click run.bat, "Run as administrator".
  echo.
  pause
  exit /b 1
)
%PY% "%SKILL%\scripts\make_lut.py" "%SKILL%\looks\golden_hour.json" --install
if %errorlevel% neq 0 ( pause & exit /b 1 )
%PY% "%SKILL%\scripts\make_lut.py" "%SKILL%\looks\stage_indoor.json" --install
if %errorlevel% neq 0 ( pause & exit /b 1 )
echo.

echo [3/5] the one manual step
echo.
echo   In Resolve, on the Color page:
echo     - open project jj
echo     - select the FIRST clip on V1
echo     - press Alt+S five times, so the clip has 6 nodes
echo.
echo   The script fills those nodes in and copies the finished graph to
echo   every other clip. Node 5 stays empty on purpose - that is where the
echo   sky window goes, and a window cannot be scripted.
echo.
pause
echo.

echo [4/5] dry run - nothing is changed yet
%PY% "%SKILL%\scripts\apply_grade.py" "%~dp0graph.json" --dry-run
if %errorlevel% neq 0 ( pause & exit /b 1 )
echo.
echo   Read that. If it names the wrong clips, close this and edit
echo   jobs\jj\color\graph.json instead of applying it.
echo.
choice /c YN /m "Apply it for real"
if errorlevel 2 (
  echo Nothing was changed.
  pause
  exit /b 0
)
echo.

echo [5/5] applying...
%PY% "%SKILL%\scripts\apply_grade.py" "%~dp0graph.json"
if %errorlevel% neq 0 ( pause & exit /b 1 )
echo.

echo Saving the graph to a .drx so it survives a delete...
%PY% "%SKILL%\scripts\export_grade.py" --project jj --clip 1 --out "%~dp0." --name jj_golden_hour
echo.

echo ============================================
echo  Done. Still by hand:
echo    - node 05 SKY: switch it on, draw a gradient across the sky
echo    - list the indoor stage clips in the "trims" block of graph.json,
echo      so they pick up stage_indoor.cube instead of the sunset look
echo        apply_grade.py jobs\jj\color\graph.json --list
echo      prints the clip names to paste in
echo  Ctrl+Z on the Color page steps any of this back.
echo ============================================
pause
