@echo off
cd /d "C:\Users\subho\tradingbot\daily_topup"
echo [%DATE% %TIME%] Running daily top-up check... >> logs\scheduler.log
"C:\Users\subho\AppData\Local\Python\bin\python3.14.exe" topup_check.py
echo [%DATE% %TIME%] Done. >> logs\scheduler.log
