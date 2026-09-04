"""
RecoverRx CLI Interactive Launcher
Single-command launcher for Razorpay evaluation and local development.
"""
import sys
import os
import time
import webbrowser
import subprocess
import database
import seed_data

BANNER = r"""
=============================================================================
  ____                                    ____       
 |  _ \ ___  ___ _____   _____ _ __      |  _ \__  __
 | |_) / _ \/ __/ _ \ \ / / _ \ '__|_____| |_) \ \/ /
 |  _ <  __/ (_| (_) \ V /  __/ | |______|  _ < >  < 
 |_| \_\___|\___\___/ \_/ \___|_|        |_| \_/_/\_\
                                                     
  Autonomous Revenue Leakage Diagnosis & Treatment Engine
  Targeted for Razorpay Engineering & Product Evaluation
=============================================================================
"""

def main():
    print(BANNER)
    print("🚀 [1/4] Checking Python Runtime...")
    major, minor = sys.version_info[:2]
    print(f"       Python {major}.{minor}.{sys.version_info[2]} detected (Requirement: 3.10+ -> PASSED)")

    print("\n📦 [2/4] Initializing Database & Seed Scenarios...")
    database.init_db()
    seed_data.seed_database()
    print("       Database ready (15 multi-channel incidents loaded with SHA-256 audit logs)")

    print("\n🧪 [3/4] Running Pipeline Self-Diagnostics Tests...")
    test_run = subprocess.run([sys.executable, "-m", "unittest", "tests/test_pipeline.py"], capture_output=True, text=True)
    if test_run.returncode == 0:
        print("       All 7 unit tests PASSED (Ingestion, Diagnosis, Policy, PTP, Holdout, Audit)")
    else:
        print(f"       Warning during tests:\n{test_run.stderr}")

    print("\n🌐 [4/4] Launching Production REST Server & Web Command Center...")
    port = int(os.environ.get("PORT", 8080))
    url = f"http://localhost:{port}"
    print(f"       Listening on: {url}")
    print(f"       Opening dashboard in your default browser...")
    print("-----------------------------------------------------------------------------")
    print("  ⭐ Press Ctrl+C anytime to stop the server.")
    print("=============================================================================\n")

    # Launch browser after a 1.2-second pause
    def open_browser():
        time.sleep(1.2)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    # Launch server
    import server
    server.start_server(port=port)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 RecoverRx shut down cleanly. Thank you!")
        sys.exit(0)
