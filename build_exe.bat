@echo off
REM Maak een losse .exe van de Idle Champions app (geen Python nodig op de pc waar je het draait)
cd /d "%~dp0"
echo Installeer PyInstaller als dat nog niet bestaat...
python -m pip install pyinstaller -q
python -m pip install -r requirements.txt -q
echo.
echo Buildnummer bijwerken...
python generate_build_info.py
echo.
REM .exe kan niet overschreven worden als de app nog draait
tasklist /FI "IMAGENAME eq IdleChampionsApp.exe" 2>NUL | find /I "IdleChampionsApp.exe" >NUL
if not errorlevel 1 (
    echo IdleChampionsApp.exe draait nog. Afsluiten zodat de build kan overschrijven...
    taskkill /F /IM IdleChampionsApp.exe >NUL 2>&1
    timeout /t 2 /nobreak >NUL
)
echo Bouwen van IdleChampionsApp.exe ...
python -m PyInstaller --noconfirm IdleChampionsApp.spec
echo.
if exist "dist\IdleChampionsApp.exe" (
    echo Klaar. De .exe staat in: dist\IdleChampionsApp.exe
    echo Je kunt die map openen en IdleChampionsApp.exe daar vandaan gebruiken.
    exit /b 0
) else (
    echo Er ging iets mis. Controleer of Python en de dependencies goed geinstalleerd zijn.
    echo Tip: sluit IdleChampionsApp.exe als die nog open staat en probeer opnieuw.
    pause
    exit /b 1
)
