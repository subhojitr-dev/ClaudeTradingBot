@echo off
:: ============================================================
::  TRADING BOT SYSTEM -- ONE-TIME SETUP SCRIPT
::  Run this ONCE as Administrator to set up the entire system
::
::  What this does:
::    1. Creates all required folders
::    2. Installs all Python dependencies
::    3. Creates Windows Task Scheduler jobs for all 5 bots
::
::  Before running:
::    - Edit the CONFIG section below with YOUR credentials
::    - Make sure Python 3.x is installed
::    - Run as Administrator (right-click -> Run as administrator)
:: ============================================================

:: ============================================================
::  CONFIG -- EDIT THESE BEFORE RUNNING
:: ============================================================

:: Your Python executable path (find it by running: where python3 or where python)
set PYTHON=C:\Users\%USERNAME%\AppData\Local\Python\bin\python3.14.exe

:: Root folder where all bot files live
set ROOT=C:\Users\%USERNAME%\tradingbot

:: ============================================================
::  DO NOT EDIT BELOW THIS LINE
:: ============================================================

echo.
echo ============================================================
echo  TRADING BOT SYSTEM -- SETUP
echo ============================================================
echo.

:: Check Administrator
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo ERROR: Please run this script as Administrator.
    echo Right-click SETUP.cmd and select "Run as administrator"
    pause
    exit /b 1
)

:: Check Python exists
if not exist "%PYTHON%" (
    echo ERROR: Python not found at: %PYTHON%
    echo Please update the PYTHON variable at the top of this script.
    echo To find your Python path, open Command Prompt and run: where python
    pause
    exit /b 1
)

echo [1/5] Python found: %PYTHON%
echo.

:: ============================================================
::  STEP 1: Create folder structure
:: ============================================================
echo [2/5] Creating folder structure...

mkdir "%ROOT%\trailing_stop\logs" 2>nul
mkdir "%ROOT%\copytrade\logs"     2>nul
mkdir "%ROOT%\flywheel\logs"      2>nul
mkdir "%ROOT%\daily_topup\logs"   2>nul

echo       Folders created.
echo.

:: ============================================================
::  STEP 2: Install Python dependencies
:: ============================================================
echo [3/5] Installing Python dependencies...
echo       (This may take 1-2 minutes)
echo.

%PYTHON% -m pip install --upgrade pip --quiet

%PYTHON% -m pip install requests beautifulsoup4 playwright --quiet

:: Install Playwright browser (needed for Capitol Trades scraping)
%PYTHON% -m playwright install chromium --quiet

echo       Dependencies installed.
echo.

:: ============================================================
::  STEP 3: Create batch launcher files
:: ============================================================
echo [4/5] Creating launcher batch files...

:: -- Trailing Stop Bot --
(
echo @echo off
echo cd /d "%ROOT%\trailing_stop"
echo "%PYTHON%" bot.py >> logs\trailing.log 2^>^&1
) > "%ROOT%\trailing_stop\run_trailing.bat"

:: -- Copy Trade Bot --
(
echo @echo off
echo cd /d "%ROOT%\copytrade"
echo "%PYTHON%" bot.py >> logs\copytrade.log 2^>^&1
) > "%ROOT%\copytrade\run_bot.bat"

:: -- Flywheel Bot --
(
echo @echo off
echo cd /d "%ROOT%\flywheel"
echo "%PYTHON%" bot.py >> logs\flywheel.log 2^>^&1
) > "%ROOT%\flywheel\run_flywheel.bat"

:: -- Flywheel Report --
(
echo @echo off
echo cd /d "%ROOT%\flywheel"
echo "%PYTHON%" report.py >> logs\report.log 2^>^&1
) > "%ROOT%\flywheel\run_report.bat"

:: -- Daily Topup Check --
(
echo @echo off
echo cd /d "%ROOT%\daily_topup"
echo "%PYTHON%" topup_check.py >> logs\topup.log 2^>^&1
) > "%ROOT%\daily_topup\run_topup.bat"

echo       Launcher files created.
echo.

:: ============================================================
::  STEP 4: Register Windows Task Scheduler jobs
:: ============================================================
echo [5/5] Registering scheduled tasks...
echo.

:: -- Delete old tasks if they exist (clean reinstall) --
schtasks /delete /tn "TrailingStopBot" /f >nul 2>&1
schtasks /delete /tn "CopyTradeBot"    /f >nul 2>&1
schtasks /delete /tn "FlywheelBot"     /f >nul 2>&1
schtasks /delete /tn "FlywheelReport"  /f >nul 2>&1
schtasks /delete /tn "DailyTopup"      /f >nul 2>&1

:: -- Trailing Stop Bot: Every 30 min, Mon-Fri 9:30 AM - 4:00 PM --
schtasks /create /tn "TrailingStopBot" ^
  /tr "\"%ROOT%\trailing_stop\run_trailing.bat\"" ^
  /sc MINUTE /mo 30 ^
  /sd 01/01/2025 /st 09:30 /et 16:00 ^
  /k /d MON,TUE,WED,THU,FRI ^
  /ru "%USERNAME%" ^
  /f >nul

if %errorLevel% EQU 0 (
    echo       [OK] TrailingStopBot     -- Every 30 min, Mon-Fri 9:30 AM - 4:00 PM
) else (
    echo       [FAIL] TrailingStopBot -- see error above
)

:: -- Copy Trade Bot: Every 30 min, Mon-Fri 9:30 AM - 4:00 PM --
schtasks /create /tn "CopyTradeBot" ^
  /tr "\"%ROOT%\copytrade\run_bot.bat\"" ^
  /sc MINUTE /mo 30 ^
  /sd 01/01/2025 /st 09:30 /et 16:00 ^
  /k /d MON,TUE,WED,THU,FRI ^
  /ru "%USERNAME%" ^
  /f >nul

if %errorLevel% EQU 0 (
    echo       [OK] CopyTradeBot        -- Every 30 min, Mon-Fri 9:30 AM - 4:00 PM
) else (
    echo       [FAIL] CopyTradeBot -- see error above
)

:: -- Flywheel Bot: Every 30 min, Mon-Fri 9:30 AM - 3:45 PM --
schtasks /create /tn "FlywheelBot" ^
  /tr "\"%ROOT%\flywheel\run_flywheel.bat\"" ^
  /sc MINUTE /mo 30 ^
  /sd 01/01/2025 /st 09:30 /et 15:45 ^
  /k /d MON,TUE,WED,THU,FRI ^
  /ru "%USERNAME%" ^
  /f >nul

if %errorLevel% EQU 0 (
    echo       [OK] FlywheelBot         -- Every 30 min, Mon-Fri 9:30 AM - 3:45 PM
) else (
    echo       [FAIL] FlywheelBot -- see error above
)

:: -- Flywheel Report: Daily at 4:00 PM, Mon-Fri --
schtasks /create /tn "FlywheelReport" ^
  /tr "\"%ROOT%\flywheel\run_report.bat\"" ^
  /sc WEEKLY ^
  /sd 01/01/2025 /st 16:00 ^
  /d MON,TUE,WED,THU,FRI ^
  /ru "%USERNAME%" ^
  /f >nul

if %errorLevel% EQU 0 (
    echo       [OK] FlywheelReport      -- Daily at 4:00 PM, Mon-Fri
) else (
    echo       [FAIL] FlywheelReport -- see error above
)

:: -- Daily Topup Check: Daily at 9:00 AM, Mon-Fri --
schtasks /create /tn "DailyTopup" ^
  /tr "\"%ROOT%\daily_topup\run_topup.bat\"" ^
  /sc WEEKLY ^
  /sd 01/01/2025 /st 09:00 ^
  /d MON,TUE,WED,THU,FRI ^
  /ru "%USERNAME%" ^
  /f >nul

if %errorLevel% EQU 0 (
    echo       [OK] DailyTopup          -- Daily at 9:00 AM, Mon-Fri
) else (
    echo       [FAIL] DailyTopup -- see error above
)

echo.
echo ============================================================
echo  SETUP COMPLETE
echo ============================================================
echo.
echo  All 5 tasks are now registered in Windows Task Scheduler.
echo  Open Task Scheduler (taskschd.msc) to verify.
echo.
echo  NEXT STEPS:
echo  1. Edit config files with YOUR Alpaca API keys and Gmail
echo     password before the bots run for the first time:
echo.
echo     %ROOT%\trailing_stop\config.py
echo     %ROOT%\copytrade\config.py
echo     %ROOT%\flywheel\config.py
echo.
echo  2. Check logs anytime at:
echo     %ROOT%\trailing_stop\logs\
echo     %ROOT%\copytrade\logs\
echo     %ROOT%\flywheel\logs\
echo.
echo  3. To verify tasks are running:
echo     schtasks /query /fo TABLE ^| findstr "Bot Report Topup"
echo.
echo  Once configs are set, the system runs fully automatically.
echo  You will receive email alerts for all trading activity.
echo.
echo  DOCUMENTATION:
echo  Read these files to understand the full system:
echo.
echo    README.md  -- Complete strategy guide with diagrams and
echo                  worked examples for every bot. Start here.
echo                  Located at: %ROOT%\README.md
echo.
echo    FILES.md   -- Detailed description of every file in the
echo                  system, what it does, and how it fits together.
echo                  Located at: %ROOT%\FILES.md
echo.
pause
