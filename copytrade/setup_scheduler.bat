@echo off
:: ============================================================
::  setup_scheduler.bat
::  Creates a Windows Task Scheduler task that runs the
::  copy-trading bot every hour, Mon–Fri, 9:30 AM – 4:00 PM ET
::
::  Data source:
::    https://www.capitoltrades.com/trades?politician=P000197
::    (Nancy Pelosi trades, rendered via Playwright/Chromium)
::
::  Run this script ONCE as Administrator to register the task.
:: ============================================================

set TASK_NAME=CopyTradingBot_Pelosi
set BOT_SCRIPT=C:\Users\subho\tradingbot\copytrade\run_bot.bat

echo.
echo ============================================================
echo  Copy-Trading Bot  ^|  Task Scheduler Setup
echo  Task   : %TASK_NAME%
echo  Script : %BOT_SCRIPT%
echo  Source : https://www.capitoltrades.com/trades?politician=P000197
echo  Target : Nancy Pelosi (D-CA)  ^|  Alpaca Paper Trading
echo  Runs   : Mon-Fri, every 60 min, 09:30-16:00 ET
echo ============================================================
echo.

:: Remove existing task if present
schtasks /Delete /TN "%TASK_NAME%" /F 2>nul

:: Create the scheduled task
::   /SC WEEKLY  /D MON,TUE,WED,THU,FRI   – weekdays only
::   /ST 09:30                             – first run at market open
::   /DU 0006:30                           – run window = 6h 30m
::   /RI 60                               – repeat every 60 minutes
::   /RL HIGHEST                          – run with highest privileges
schtasks /Create ^
  /TN "%TASK_NAME%" ^
  /TR "\"%BOT_SCRIPT%\"" ^
  /SC WEEKLY ^
  /D MON,TUE,WED,THU,FRI ^
  /ST 09:30 ^
  /DU 0006:30 ^
  /RI 60 ^
  /F ^
  /RL HIGHEST ^
  /RU "%USERNAME%"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [OK] Task "%TASK_NAME%" created successfully!
    echo      Schedule: Mon-Fri, every 60 min from 09:30 to 16:00
    echo.
    echo      To run immediately for testing:
    echo      schtasks /Run /TN "%TASK_NAME%"
    echo.
    echo      To view task status:
    echo      schtasks /Query /TN "%TASK_NAME%" /FO LIST
) else (
    echo.
    echo [ERROR] Failed to create task.
    echo         Please right-click this .bat file and choose
    echo         "Run as Administrator", then try again.
)

echo.
schtasks /Query /TN "%TASK_NAME%" /FO LIST 2>nul
echo.
pause
