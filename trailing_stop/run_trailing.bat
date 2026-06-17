@echo off
:: Trailing Stop Strategy Monitor
:: Scheduled every 30 minutes Mon-Fri 9:30 AM - 4:00 PM ET
cd /d "C:\Users\subho\tradingbot\trailing_stop"
echo [%DATE% %TIME%] Running trailing stop bot... >> logs\scheduler.log
"C:\Users\subho\AppData\Local\Python\bin\python3.14.exe" bot.py >> logs\scheduler.log 2>&1
echo [%DATE% %TIME%] Done (exit=%ERRORLEVEL%). >> logs\scheduler.log
