@echo off
setlocal

cd /d "C:\Users\festa\Desktop\git_repos\datenflix007\NARA-Trace" || goto error
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
exit /b %ERRORLEVEL%

:usage
echo.
echo Verwendung:
echo   .\quickstart.bat       Anwendung starten
echo   .\quickstart.bat index A3340-Gesamtindex aufbauen oder fortsetzen
echo   .\quickstart.bat all   Index aufbauen und danach Anwendung starten
endlocal
exit /b 2

:error
echo.
echo [FEHLER] NARA-Trace konnte nicht gestartet werden.
echo Fehlercode: %ERRORLEVEL%
pause
endlocal
exit /b 1
