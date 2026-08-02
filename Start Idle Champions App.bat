@echo off

REM Start de Idle Champions automatisering-app (Windows)

cd /d "%~dp0"

python --version >nul 2>&1

if errorlevel 1 (

    echo Python is niet geinstalleerd of niet in het pad.

    echo Installeer Python van https://www.python.org/downloads/

    pause

    exit /b 1

)

if not exist "app_launcher.py" (

    echo Bestand app_launcher.py niet gevonden.

    pause

    exit /b 1

)

pip install -r requirements.txt -q 2>nul

set "QT_QPA_PLATFORM=windows:dpiawareness=1"

REM Gebruik pythonw zodat er geen zwart console-venster flitst naast de GUI.
where pythonw >nul 2>&1
if errorlevel 1 (
    start "" /B python app_launcher.py
) else (
    start "" pythonw app_launcher.py
)

exit /b 0

