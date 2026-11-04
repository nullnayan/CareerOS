@echo off
echo Starting CareerOS Frontend...
if not defined NEXT_PUBLIC_CAREEROS_API_BASE set "NEXT_PUBLIC_CAREEROS_API_BASE=http://127.0.0.1:8010"
npm run dev -- --hostname 127.0.0.1 --port 3000
