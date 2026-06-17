@echo off
:: ============================================================
::  run_bot.bat  –  Launches the multi-politician copy-trading bot
::  Called by Windows Task Scheduler every 30 min on weekdays
::  Politicians: Pelosi (P000197), McCaul (M001157), Ro Khanna (K000389)
:: ============================================================
cd /d "C:\Users\subho\tradingbot\copytrade"

echo [%DATE% %TIME%] Starting copy-trading bot... >> logs\scheduler.log

"C:\Users\subho\AppData\Local\Python\bin\python3.14.exe" bot.py >> logs\scheduler.log 2>&1

echo [%DATE% %TIME%] Bot run complete (exit code: %ERRORLEVEL%). >> logs\scheduler.log
