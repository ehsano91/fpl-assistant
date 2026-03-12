"""
scheduler.py  —  Pipeline Runner + macOS Auto-Scheduler
---------------------------------------------------------
Runs the full data pipeline in order:
  1. engine/fetch_fpl.py   — download fresh data from the FPL API
  2. engine/model.py       — recalculate expected points

Usage:
  python3 engine/scheduler.py --test      Run the pipeline right now
  python3 engine/scheduler.py --install   Install a macOS launchd job
                                          that runs every day at 07:00
  python3 engine/scheduler.py             Print this help text

The --install flag writes a plist to ~/Library/LaunchAgents/ and loads
it with launchctl.  To uninstall later:
  launchctl unload ~/Library/LaunchAgents/com.fpl-assistant.scheduler.plist
  rm ~/Library/LaunchAgents/com.fpl-assistant.scheduler.plist
"""

import subprocess
import sys
import os
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Absolute path to the fpl-assistant/ project root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Scripts to run in order (each must exit 0 for the pipeline to continue)
PIPELINE = [
    os.path.join(PROJECT_ROOT, "engine", "fetch_fpl.py"),
    os.path.join(PROJECT_ROOT, "engine", "model.py"),
    os.path.join(PROJECT_ROOT, "engine", "qualitative.py"),
    os.path.join(PROJECT_ROOT, "engine", "ai_recommend.py"),
]

# macOS launchd identifiers
PLIST_LABEL = "com.fpl-assistant.scheduler"
PLIST_DIR   = os.path.expanduser("~/Library/LaunchAgents")
PLIST_PATH  = os.path.join(PLIST_DIR, f"{PLIST_LABEL}.plist")

# Log file that launchd will write stdout/stderr to
LOG_PATH = os.path.join(PROJECT_ROOT, "engine", "scheduler.log")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def banner(msg):
    """Print a visually separated section header."""
    width = 60
    print(f"\n{'=' * width}")
    print(f"  {msg}")
    print(f"{'=' * width}")


def run_step(script_path):
    """
    Run one Python script as a subprocess using the same interpreter
    that is running this file.  Output is streamed live to the terminal.

    Returns True on success (exit code 0), False on failure.
    """
    label  = os.path.basename(script_path)
    python = sys.executable          # e.g. /usr/local/bin/python3

    print(f"\n[STEP] {label}")
    print(f"  {'─' * 55}")

    result = subprocess.run(
        [python, script_path],
        cwd=PROJECT_ROOT,            # run from the project root so relative paths work
    )

    print(f"  {'─' * 55}")
    if result.returncode == 0:
        print(f"  [OK]   {label} finished successfully.")
        return True
    else:
        print(f"  [FAIL] {label} exited with code {result.returncode}.")
        return False


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline():
    """Run every script in PIPELINE in order.  Abort on first failure."""
    banner("FPL Assistant — Full Data Pipeline")
    print(f"  Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Project : {PROJECT_ROOT}")

    for script in PIPELINE:
        if not os.path.exists(script):
            print(f"\n  [ERROR] Script not found: {script}")
            print("  Make sure you're running from the fpl-assistant/ directory.")
            sys.exit(1)

        success = run_step(script)
        if not success:
            banner(f"Pipeline aborted — {os.path.basename(script)} failed")
            sys.exit(1)

    banner("Pipeline complete!")
    print(f"  Finished : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  db/fpl.db is up to date.")
    print(f"  Restart engine/api_server.py to serve fresh data.\n")


# ---------------------------------------------------------------------------
# macOS launchd installer
# ---------------------------------------------------------------------------

def install_launchd():
    """
    Write a launchd plist that runs the pipeline every day at 07:00
    and load it immediately with launchctl.

    launchd is macOS's built-in job scheduler (like cron, but it handles
    machine sleep/wake properly and integrates with the login session).
    """
    banner("Installing macOS launchd Job")

    python = sys.executable
    script = os.path.join(PROJECT_ROOT, "engine", "scheduler.py")

    # The plist is standard Apple XML — launchd reads it on login
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>

    <!-- Unique label for this job — must be globally unique on this Mac -->
    <key>Label</key>
    <string>{PLIST_LABEL}</string>

    <!-- Command to run: python3 engine/scheduler.py --test -->
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>{script}</string>
        <string>--test</string>
    </array>

    <!-- Run every day at 00:00 local time -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>0</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <!-- Working directory — so relative paths inside the scripts work -->
    <key>WorkingDirectory</key>
    <string>{PROJECT_ROOT}</string>

    <!-- Write stdout and stderr to a log file for debugging -->
    <key>StandardOutPath</key>
    <string>{LOG_PATH}</string>
    <key>StandardErrorPath</key>
    <string>{LOG_PATH}</string>

    <!-- Do NOT run immediately at login if the scheduled time was missed -->
    <key>RunAtLoad</key>
    <false/>

</dict>
</plist>
"""

    # Make sure ~/Library/LaunchAgents/ exists (it always should on macOS)
    os.makedirs(PLIST_DIR, exist_ok=True)

    # Write the plist file
    with open(PLIST_PATH, "w") as f:
        f.write(plist)
    print(f"  Plist written : {PLIST_PATH}")

    # Load it so launchd knows about it immediately (no reboot needed)
    print(f"  Loading with  : launchctl load {PLIST_PATH}")
    result = subprocess.run(
        ["launchctl", "load", PLIST_PATH],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print("  [OK] Job loaded — pipeline will run every day at 07:00.")
    else:
        msg = (result.stderr or result.stdout).strip()
        print(f"  [WARN] launchctl: {msg}")
        print(f"  You can load it manually:")
        print(f"    launchctl load {PLIST_PATH}")

    print(f"\n  Logs will appear in: {LOG_PATH}")
    print(f"\n  To uninstall:")
    print(f"    launchctl unload {PLIST_PATH}")
    print(f"    rm {PLIST_PATH}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def print_help():
    print("\nUsage:")
    print("  python3 engine/scheduler.py --test      Run the pipeline right now")
    print("  python3 engine/scheduler.py --install   Install daily 07:00 auto-run (macOS)")
    print()


if __name__ == "__main__":
    if "--test" in sys.argv:
        run_pipeline()
    elif "--install" in sys.argv:
        install_launchd()
    else:
        print_help()
