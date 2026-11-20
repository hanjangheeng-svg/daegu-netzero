@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [Daegu NetZero] Checking Python packages...
python -m pip install -r requirements.txt || goto :error
echo [Daegu NetZero] Installing React packages...
cd frontend
call npm install || goto :error
call npm run build || goto :error
cd ..
echo [Daegu NetZero] Starting at http://127.0.0.1:8504
start "" "http://127.0.0.1:8504"
python -m uvicorn backend.api:app --host 127.0.0.1 --port 8504
pause
exit /b
:error
echo.
echo Installation failed. Check that Python and Node.js are installed.
pause
