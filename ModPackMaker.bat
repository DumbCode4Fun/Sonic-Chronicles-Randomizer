@echo off
REM ---------------------------------------------------------------------------
REM  Sonic Chronicles Mod Pack Maker - run from source.
REM
REM  Needs Python 3.8 or newer with tkinter, which the installer from
REM  https://www.python.org/downloads/ includes by default. Tick
REM  "Add python.exe to PATH" on the first screen, or this cannot find it.
REM
REM  Nothing else to install. The tool reads the ROM you point it at and
REM  never writes to it.
REM
REM  This launches through pyw/pythonw, the *windowed* Python, so no black
REM  console window opens alongside the app. The console build is kept as a
REM  fallback for a Python install that somehow lacks the windowed launcher;
REM  if the app fails to start it says so in a dialog either way.
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

where pyw >nul 2>nul
if not errorlevel 1 goto :use_pyw
where pythonw >nul 2>nul
if not errorlevel 1 goto :use_pythonw
where py >nul 2>nul
if not errorlevel 1 goto :use_py
where python >nul 2>nul
if not errorlevel 1 goto :use_python
goto :no_python

:use_pyw
start "" pyw -3 "tools\gui\modpack_maker.py" %*
goto :eof

:use_pythonw
start "" pythonw "tools\gui\modpack_maker.py" %*
goto :eof

:use_py
py -3 "tools\gui\modpack_maker.py" %*
goto :finished

:use_python
python "tools\gui\modpack_maker.py" %*
goto :finished

:no_python
echo.
echo   Python was not found on this PC.
echo.
echo   Install it from  https://www.python.org/downloads/  and tick
echo   "Add python.exe to PATH" on the first screen of the installer,
echo   then run this file again.
echo.
pause
exit /b 1

:finished
if errorlevel 1 (
    echo.
    echo   The Mod Pack Maker exited with an error; the message above says why.
    pause
)
exit /b
