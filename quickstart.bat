@echo off
setlocal

rem Always start from the directory containing this file.  The project may be
rem moved, so an absolute developer-specific path must not be used here.
cd /d "%~dp0" || goto error
if not exist "backend\naratrace\__main__.py" goto missing_project_files
if not exist "frontend\package.json" goto missing_project_files
set "PYTHONPATH=%CD%\backend"
set "MODE=%~1"

if /I "%MODE%"=="index" goto index
if /I "%MODE%"=="all" goto index_then_start
if not "%MODE%"=="" goto usage

echo.
echo [1/2] Frontend wird gebaut...
pushd "frontend"

call npm run build
if errorlevel 1 goto error

popd

echo.
echo [2/2] NARA-Trace wird gestartet...

python -m naratrace --port 8766
if errorlevel 1 goto error

endlocal
exit /b 0

:missing_project_files
echo.
echo [FEHLER] Die Projektdateien wurden neben quickstart.bat nicht gefunden.
echo Bitte quickstart.bat im NARA-Trace-Ordner ausfuehren.
goto error

:index
echo.
echo A3340-Gesamtindex wird aufgebaut bzw. fortgesetzt...
echo Das laedt alle MFKL- und MFOK-Roll-JSONs, aber keine Kartenbilder in Masse.
python -m naratrace --index-a3340
if errorlevel 1 goto error
echo.
echo Fertig. Jetzt .\quickstart.bat zum Starten der Anwendung ausfuehren.
endlocal
exit /b 0

:index_then_start
call "%~f0" index
if errorlevel 1 goto error
call "%~f0"
set "QUICKSTART_ERROR=%ERRORLEVEL%"
endlocal
exit /b %QUICKSTART_ERROR%

:usage
echo.
echo Verwendung:
echo   .\quickstart.bat       Anwendung starten
echo   .\quickstart.bat index A3340-Gesamtindex aufbauen oder fortsetzen
echo   .\quickstart.bat all   Index aufbauen und danach Anwendung starten
endlocal
exit /b 2

:error
set "QUICKSTART_ERROR=%ERRORLEVEL%"
echo.
echo [FEHLER] NARA-Trace konnte nicht gestartet werden.
echo Fehlercode: %QUICKSTART_ERROR%
pause
endlocal
exit /b 1
