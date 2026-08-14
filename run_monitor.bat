@echo off

cd /d C:\Users\shaha\Documents\DS_projects\zansdi-rendering-monitor

if not exist artifacts\logs mkdir artifacts\logs

.venv\Scripts\python.exe monitor.py >> artifacts\logs\monitor.log 2>&1