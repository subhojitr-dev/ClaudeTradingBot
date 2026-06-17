@echo off
:: ============================================================
::  Wheel Strategy Bot launcher
::  Runs every 30 min Mon-Fri 9:30 AM - 4:00 PM ET
::  Account: PA34EFPV3B80
:: ============================================================
cd /d "C:\Users\subho\tradingbot\flywheel"
echo [%DATE% %TIME%] Flywheel bot starting... >> logs\scheduler.log
"C:\Users\subho\AppData\Local\Python\bin\python3.14.exe" bot.py >> logs\scheduler.log 2>&1
echo [%DATE% %TIME%] Done (exit=%ERRORLEVEL%). >> logs\scheduler.log
