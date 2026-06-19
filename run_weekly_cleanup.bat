@echo off
cd /d C:\Users\subho\tradingbot
python email_archive.py >> logs\weekly_cleanup.log 2>&1
