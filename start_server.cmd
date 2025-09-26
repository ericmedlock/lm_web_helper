@echo off
setlocal enableextensions

REM === project dir ===
cd /d C:\Users\ericm\PycharmProjects\lm_web_helper

REM === env for your helper (adjust as needed) ===
set LM_BASE=http://localhost:1234/v1
set LM_MODEL=meta-llama-3.1-8b-instruct

REM === activate venv ===
call .venv\Scripts\activate

REM === run forever; always start even if LM Studio isn't up yet ===
:boot
echo [%date% %time%] starting uvicorn >> server.log
python -m uvicorn server:app --host 127.0.0.1 --port 5055 --workers 1 --log-level info >> server.log 2>&1
echo [%date% %time%] uvicorn exited with %errorlevel%, waiting 5s and restarting >> server.log
timeout /t 5 /nobreak >nul
goto boot
