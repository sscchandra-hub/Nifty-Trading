@echo off
REM ===================================================
REM   NIFTY TRADING DASHBOARD - OPTIMIZED LAUNCHER
REM   Starts dashboard + Chrome with 8-hour stability
REM ===================================================

echo.
echo ========================================
echo   APEX AI TRADING - Starting...
echo ========================================
echo.

REM Start Streamlit in background
echo [1/2] Starting Streamlit dashboard...
start "Streamlit Server" cmd /c "streamlit run app.py"

REM Wait for Streamlit to start
echo [2/2] Waiting for server to start...
timeout /t 8 /nobreak >nul

REM Launch Chrome with performance flags for 8-hour sessions
echo.
echo Opening optimized Chrome...
echo.
"C:\Program Files\Google\Chrome\Application\chrome.exe" --new-window --disable-background-timer-throttling --disable-renderer-backgrounding --disable-backgrounding-occluded-windows --disable-features=CalculateNativeWinOcclusion --enable-features=MemoryCoordinator --js-flags="--max-old-space-size=8192" --max-old-space-size=8192 --disable-dev-shm-usage --disable-gpu-compositing http://localhost:8501

echo.
echo ========================================
echo   Dashboard running!
echo   Close this window to stop server
echo ========================================
echo.
pause
