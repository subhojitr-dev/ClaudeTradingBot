@echo off
cd /d C:\Users\subho\tradingbot\reports
C:\Users\subho\AppData\Local\Python\bin\python3.14.exe daily_report.py >> logs\scheduler.log 2>&1
