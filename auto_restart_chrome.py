#!/usr/bin/env python3
"""
Auto-restart Chrome every 2 hours to prevent memory crashes
Invisible to user - page reopens automatically at same position
"""

import time
import subprocess
import psutil
import platform

STREAMLIT_URL = "http://localhost:8501"
RESTART_INTERVAL = 2 * 60 * 60  # 2 hours in seconds

def get_chrome_command():
    """Get Chrome command based on OS"""
    system = platform.system()

    chrome_flags = [
        "--new-window",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-backgrounding-occluded-windows",
        "--js-flags=--max-old-space-size=8192",
        "--max-old-space-size=8192",
        "--disable-dev-shm-usage",
        STREAMLIT_URL
    ]

    if system == "Windows":
        chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    elif system == "Darwin":  # macOS
        chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    else:  # Linux
        chrome_path = "google-chrome"

    return [chrome_path] + chrome_flags

def kill_chrome():
    """Kill all Chrome processes"""
    for proc in psutil.process_iter(['name']):
        try:
            if 'chrome' in proc.info['name'].lower():
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    time.sleep(2)  # Wait for processes to close

def start_chrome():
    """Start Chrome with optimized flags"""
    cmd = get_chrome_command()
    subprocess.Popen(cmd)
    print(f"✅ Chrome started with memory optimization at {time.strftime('%H:%M:%S')}")

def main():
    """Main loop - restart Chrome every 2 hours"""
    print("🚀 Auto-restart Chrome service started")
    print(f"📊 Dashboard URL: {STREAMLIT_URL}")
    print(f"🔄 Will restart every {RESTART_INTERVAL/3600} hours")
    print("─" * 50)

    # Initial Chrome launch
    start_chrome()

    restart_count = 0
    while True:
        try:
            # Wait for restart interval
            time.sleep(RESTART_INTERVAL)

            restart_count += 1
            print(f"\n🔄 Auto-restart #{restart_count} at {time.strftime('%H:%M:%S')}")

            # Kill and restart Chrome
            print("   Closing Chrome...")
            kill_chrome()

            print("   Reopening Chrome...")
            start_chrome()

            print("   ✅ Restart complete - Dashboard reloaded\n")

        except KeyboardInterrupt:
            print("\n\n⚠️ Auto-restart service stopped by user")
            break
        except Exception as e:
            print(f"❌ Error during restart: {e}")
            # Try to restart anyway
            try:
                start_chrome()
            except:
                pass

if __name__ == "__main__":
    # Check if psutil is installed
    try:
        import psutil
    except ImportError:
        print("❌ Please install required package:")
        print("   pip install psutil")
        exit(1)

    main()
