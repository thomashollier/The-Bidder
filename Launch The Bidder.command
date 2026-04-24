#!/bin/bash
# =============================================================
# The Bidder — macOS Launcher
# Double-click this file to start the app.
# =============================================================

# Navigate to the script's directory
cd "$(dirname "$0")"

# Clear the terminal for a clean look
clear

# Run the launcher
python3 launch.py

# Keep terminal open if something goes wrong
if [ $? -ne 0 ]; then
    echo ""
    echo "  Something went wrong. Check the errors above."
    echo "  Press any key to close."
    read -n 1
fi
