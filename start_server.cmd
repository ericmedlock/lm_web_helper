@echo off
setlocal
REM ==== adjust this path if your project lives elsewhere ====
cd /d C:\Users\ericm\PycharmProjects\lm_web_helper

REM ---- env for your helper (safe to keep local on this box) ----
set LM_BASE=http://localhost:1234/v1
set LM_MODEL=meta-llama-3.1-8b-instruct
REM Put your real key here (or remove this line if you set it in Windows user env)
set TAVILY_API_KEY=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


REM ---- wait for LM Studio local server to be up on port 1234 (30 tries ~60s) ----
for /l %%i in (1,1,30) do (
  powershell -NoLogo -NoProfile -Command "$u='http://localhost:1234/v1/models'; try { (Invoke-WebRequest -UseBasicParsing -Uri $u -TimeoutSec 2) | Out-Null; exit 0 } catch { Start-Sleep -Seconds 2; exit 1 }"
  if %errorlevel%==0 goto :ready
)
echo [start_server] LM Studio API not reachable on :1234 after ~60s. Exiting.
exit /b 1

:ready
call .venv\Scripts\activate
python -m uvicorn server:app --host 127.0.0.1 --port 5055 --workers 1 --log-level info
