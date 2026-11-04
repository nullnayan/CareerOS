@echo off
echo Starting CareerOS Backend...
call .\venv\Scripts\activate
if not defined CAREEROS_API_PORT set "CAREEROS_API_PORT=8010"
uvicorn main:app --host 127.0.0.1 --port %CAREEROS_API_PORT% --reload
