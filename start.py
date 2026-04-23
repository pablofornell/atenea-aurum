#!/usr/bin/env python3
"""Aurum Automated Startup — Handles all initialization steps."""
import os
import sys
import subprocess
import time
import socket
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s — %(message)s"
)
logger = logging.getLogger(__name__)

REPO_DIR = Path(__file__).parent
MT4_PATH = r"C:\Program Files (x86)\NMarkets Limited MT4 Terminal"
MT4_EXPERTS = MT4_PATH / "MQL4" / "Experts"
OPS_DIR = REPO_DIR / "ops"


def step(msg: str):
    """Log a step."""
    logger.info(f"\n{'='*70}\n  {msg}\n{'='*70}")


def check_python_deps():
    """Install Python dependencies."""
    step("1️⃣  CHECKING PYTHON DEPENDENCIES")
    req_file = REPO_DIR / "requirements.txt"
    if not req_file.exists():
        logger.error(f"requirements.txt not found at {req_file}")
        return False

    try:
        logger.info("Installing packages from requirements.txt...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "-r", str(req_file)],
            cwd=str(REPO_DIR),
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logger.error(f"pip install failed:\n{result.stderr}")
            return False
        logger.info("✓ Python dependencies installed")
        return True
    except Exception as e:
        logger.error(f"Failed to install dependencies: {e}")
        return False


def install_ea_files():
    """Install EA and headers to MT4."""
    step("2️⃣  INSTALLING EXPERT ADVISOR TO MT4")

    if not MT4_PATH.exists():
        logger.error(f"MT4 path not found: {MT4_PATH}")
        logger.error("Please update MT4_PATH in start.py if using a different location")
        return False

    # Run PowerShell install script
    ps_script = OPS_DIR / "install_ea.ps1"
    if not ps_script.exists():
        logger.error(f"install_ea.ps1 not found at {ps_script}")
        return False

    try:
        logger.info(f"Running install_ea.ps1...")
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ps_script), "-MT4Path", str(MT4_PATH)],
            capture_output=True,
            text=True,
            cwd=str(OPS_DIR)
        )
        logger.info(result.stdout)
        if result.returncode != 0:
            logger.error(f"PowerShell script failed:\n{result.stderr}")
            return False
        logger.info("✓ EA files installed to MT4")
        return True
    except Exception as e:
        logger.error(f"Failed to run install script: {e}")
        return False


def check_ea_compiled():
    """Check if EA is compiled."""
    step("3️⃣  CHECKING IF EA IS COMPILED")

    # Look for .ex4 file
    ea_compiled = MT4_EXPERTS / "AURUM_Bridge.ex4"
    ea_source = MT4_EXPERTS / "AURUM_Bridge.mq4"

    if not ea_source.exists():
        logger.error(f"EA source not found: {ea_source}")
        return False

    if ea_compiled.exists():
        logger.info("✓ EA is already compiled (.ex4 found)")
        return True

    logger.warning("EA is not compiled yet")
    logger.warning("\n🔧 MANUAL STEP REQUIRED:")
    logger.warning("1. Open MetaTrader 4")
    logger.warning("2. Press Ctrl+E to open MetaEditor")
    logger.warning("3. Open: MQL4/Experts/AURUM_Bridge.mq4")
    logger.warning("4. Press F5 to compile")
    logger.warning("5. Verify: '0 errors' appears in the output panel")
    logger.warning("6. Close MetaEditor and return here")
    logger.warning("\nPress Enter when you've completed compilation...")

    try:
        input()
        if ea_compiled.exists():
            logger.info("✓ EA compilation confirmed")
            return True
        else:
            logger.error("EA compilation not detected. Please compile manually.")
            return False
    except KeyboardInterrupt:
        logger.error("Aborted by user")
        return False


def check_dll_imports_enabled():
    """Remind user to enable DLL imports."""
    step("4️⃣  CHECKING DLL IMPORTS PERMISSION")

    logger.warning("🔧 MANUAL STEP REQUIRED:")
    logger.warning("In MetaTrader 4, enable DLL imports:")
    logger.warning("1. Tools → Options")
    logger.warning("2. Expert Advisors tab")
    logger.warning("3. Check '✓ Allow DLL imports'")
    logger.warning("4. Click OK")
    logger.warning("\nPress Enter when you've enabled DLL imports...")

    try:
        input()
        logger.info("✓ DLL imports permission assumed enabled")
        return True
    except KeyboardInterrupt:
        logger.error("Aborted by user")
        return False


def check_ea_attached():
    """Check if EA is attached to XAUUSD chart."""
    step("5️⃣  CHECKING IF EA IS ATTACHED TO CHART")

    logger.warning("🔧 MANUAL STEP REQUIRED:")
    logger.warning("In MetaTrader 4:")
    logger.warning("1. Open XAUUSD chart")
    logger.warning("2. Right-click on chart → Expert Advisors → Attach Expert Advisor")
    logger.warning("3. Select: AURUM_Bridge")
    logger.warning("4. Click OK")
    logger.warning("5. Verify: Green 😊 smiley appears on chart top-right")
    logger.warning("\nPress Enter when you see the green smiley...")

    try:
        input()
        logger.info("✓ EA attachment confirmed")
        return True
    except KeyboardInterrupt:
        logger.error("Aborted by user")
        return False


def wait_for_mt4_connection(timeout: int = 30):
    """Wait for MT4 to respond on port 5555."""
    step("6️⃣  WAITING FOR MT4 TCP SERVER")

    logger.info(f"Checking if MT4 is listening on 127.0.0.1:5555...")
    start = time.time()

    while time.time() - start < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("127.0.0.1", 5555))
            sock.close()

            if result == 0:
                logger.info("✓ MT4 TCP server is ready!")
                return True
        except Exception:
            pass

        elapsed = int(time.time() - start)
        print(f"\r  Waiting... {elapsed}s", end="", flush=True)
        time.sleep(1)

    print()
    logger.error(f"MT4 did not respond within {timeout}s")
    logger.error("Troubleshooting:")
    logger.error("- Check that EA has green smiley on chart")
    logger.error("- Run: netstat -an | findstr 5555")
    logger.error("- Check MT4 Experts tab for errors")
    return False


def start_aurum():
    """Start Aurum trading system."""
    step("7️⃣  STARTING AURUM TRADING SYSTEM")

    logger.info("Launching main.py...")
    logger.info("\nPress Ctrl+C to stop the system\n")

    try:
        result = subprocess.run(
            [sys.executable, "main.py"],
            cwd=str(REPO_DIR)
        )
        return result.returncode == 0
    except KeyboardInterrupt:
        logger.info("\n\nShutdown requested")
        return True
    except Exception as e:
        logger.error(f"Failed to start Aurum: {e}")
        return False


def main():
    """Run all initialization steps."""
    logger.info("""
╔════════════════════════════════════════════════════════════════════╗
║              AURUM Automated Startup Sequence                      ║
║                                                                    ║
║  This script will:                                                 ║
║  1. Install Python dependencies                                   ║
║  2. Copy EA & headers to MT4                                       ║
║  3. Guide you through manual MT4 steps (compile, attach EA)       ║
║  4. Wait for MT4 to be ready                                       ║
║  5. Launch the trading system                                      ║
╚════════════════════════════════════════════════════════════════════╝
    """)

    steps = [
        ("Python Dependencies", check_python_deps),
        ("EA Installation", install_ea_files),
        ("EA Compilation", check_ea_compiled),
        ("DLL Imports", check_dll_imports_enabled),
        ("EA Attachment", check_ea_attached),
        ("MT4 Connection", wait_for_mt4_connection),
        ("Start Aurum", start_aurum),
    ]

    for i, (name, func) in enumerate(steps, 1):
        try:
            if not func():
                logger.error(f"\n❌ Failed at step {i}: {name}")
                logger.error("Please fix the issue and run start.py again")
                return 1
        except Exception as e:
            logger.error(f"\n❌ Unexpected error in step {i}: {e}", exc_info=True)
            return 1

    logger.info("""
╔════════════════════════════════════════════════════════════════════╗
║              ✓ AURUM STARTED SUCCESSFULLY                          ║
╚════════════════════════════════════════════════════════════════════╝
    """)
    return 0


if __name__ == "__main__":
    sys.exit(main())
