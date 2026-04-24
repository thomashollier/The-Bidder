#!/usr/bin/env python3
"""
The Bidder — Launcher
=====================
Checks dependencies, installs Flask if needed, starts the web server,
and opens the browser. This is the single entry point.
"""

import importlib
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

PORT = 5050
URL = f"http://127.0.0.1:{PORT}"
ROOT = Path(__file__).parent


def check_python():
    """Ensure Python 3.10+."""
    if sys.version_info < (3, 10):
        print(f"Error: Python 3.10+ required. You have {sys.version}")
        print("Download from https://python.org")
        input("Press Enter to exit...")
        sys.exit(1)


def check_claude():
    """Check if claude CLI is available."""
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print(f"  Claude CLI: {result.stdout.strip()}")
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    print("\n  WARNING: 'claude' command not found.")
    print("  The pipeline requires Claude Code CLI to run.")
    print("  Install: https://docs.anthropic.com/en/docs/claude-code")
    print("  Then run: claude login\n")
    print("  You can still explore the UI, but pipeline stages will fail.\n")
    return False


def install_flask():
    """Install Flask if not already available."""
    try:
        importlib.import_module("flask")
        print("  Flask: installed")
        return
    except ImportError:
        pass

    print("  Flask: not found — installing...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "flask", "--quiet"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print("  Flask: installed")


def start_server():
    """Start the Flask server and open the browser."""
    print(f"\n  Starting server at {URL}")
    print("  Press Ctrl+C to stop.\n")

    # Open browser after a short delay
    def open_browser():
        time.sleep(1.5)
        webbrowser.open(URL)

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    # Import and run Flask app
    sys.path.insert(0, str(ROOT / "web"))
    os.chdir(ROOT)

    from server import app, PROJECTS_DIR
    PROJECTS_DIR.mkdir(exist_ok=True)

    app.run(host="127.0.0.1", port=PORT, debug=False)


def main():
    print()
    print("  ┌─────────────────────────────────┐")
    print("  │   The Bidder                     │")
    print("  │   VFX Breakdown Pipeline         │")
    print("  └─────────────────────────────────┘")
    print()

    check_python()
    install_flask()
    check_claude()
    start_server()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
