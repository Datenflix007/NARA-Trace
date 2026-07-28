@echo off
setlocal

cd /d "C:\Users\festa\Desktop\git_repos\datenflix007\NARA-Trace" || goto error

echo.
echo [1/2] Frontend wird gebaut...
pushd "frontend"

call npm run build
if errorlevel 1 goto error

popd

echo.
echo [2/2] NARA-Trace wird gestartet...

set "PYTHONPATH=%CD%\backend"

python -m naratrace --port 8766
if errorlevel 1 goto error

endlocal
exit /b 0

:error
echo.
echo [FEHLER] NARA-Trace konnte nicht gestartet werden.
echo Fehlercode: %ERRORLEVEL%
pause
endlocal
exit /b 1