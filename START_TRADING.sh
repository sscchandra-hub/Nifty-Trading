#!/bin/bash
# ===================================================
#   NIFTY TRADING DASHBOARD - OPTIMIZED LAUNCHER
#   Starts dashboard + Chrome with 8-hour stability
# ===================================================

echo ""
echo "========================================"
echo "   APEX AI TRADING - Starting..."
echo "========================================"
echo ""

# Start Streamlit in background
echo "[1/2] Starting Streamlit dashboard..."
nohup streamlit run app.py > streamlit.log 2>&1 &
STREAMLIT_PID=$!
echo "Streamlit PID: $STREAMLIT_PID"

# Wait for Streamlit to start
echo "[2/2] Waiting for server to start..."
sleep 8

# Launch Chrome with performance flags for 8-hour sessions
echo ""
echo "Opening optimized Chrome..."
echo ""

google-chrome \
  --new-window \
  --disable-background-timer-throttling \
  --disable-renderer-backgrounding \
  --disable-backgrounding-occluded-windows \
  --disable-features=CalculateNativeWinOcclusion \
  --enable-features=MemoryCoordinator \
  --js-flags="--max-old-space-size=8192" \
  --max-old-space-size=8192 \
  --disable-dev-shm-usage \
  --disable-gpu-compositing \
  http://localhost:8501 &

echo ""
echo "========================================"
echo "   Dashboard running!"
echo "   Streamlit PID: $STREAMLIT_PID"
echo "   To stop: kill $STREAMLIT_PID"
echo "========================================"
echo ""
