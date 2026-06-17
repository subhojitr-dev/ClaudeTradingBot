@echo off
:: ============================================================
::  Daily report -- runs at 4:00 PM ET (market close)
:: ============================================================
cd /d "C:\Users\subho\tradingbot\flywheel"
echo [%DATE% %TIME%] Daily report starting... >> logs\scheduler.log
"C:\Users\subho\AppData\Local\Python\bin\python3.14.exe" report.py >> logs\scheduler.log 2>&1
echo [%DATE% %TIME%] Report done (exit=%ERRORLEVEL%). >> logs\scheduler.log
