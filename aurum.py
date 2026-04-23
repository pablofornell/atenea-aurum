#!/usr/bin/env python3
"""Aurum trading system entry point.

Initializes MT4 connection, Claude bridge, storage, and runs the trading agent.
"""
import logging
import sys
from pathlib import Path

from src.mt4.bridge import MT4Bridge, MT4BridgeError
from src.bridge.claude_bridge import call_claude
from src.db.storage import SessionStorage
from src.agent.agent import AurumAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(name)s — %(levelname)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/aurum.log"),
    ]
)

logger = logging.getLogger(__name__)


def main():
    """Main entry point."""
    logger.info("=" * 80)
    logger.info("AURUM Trading System Starting")
    logger.info("=" * 80)

    # Initialize MT4 bridge
    logger.info("Connecting to MT4...")
    try:
        mt4 = MT4Bridge(host="127.0.0.1", port=5555, timeout=5.0)
        mt4.connect()
        pong = mt4.ping()
        if not pong:
            logger.error("MT4 ping failed")
            return 1
        logger.info("MT4 connected successfully")
    except MT4BridgeError as e:
        logger.error(f"Cannot connect to MT4: {e}")
        logger.error("Make sure AURUM_Bridge EA is running in MT4 on port 5555")
        return 1

    # Initialize storage
    logger.info("Initializing database...")
    try:
        storage = SessionStorage(db_path="data/aurum.db")
        logger.info("Database ready")
    except Exception as e:
        logger.error(f"Cannot initialize database: {e}")
        return 1

    # Create and run agent
    try:
        agent = AurumAgent(
            mt4_bridge=mt4,
            storage=storage,
            cycle_interval=900  # 15 minutes
        )
        logger.info("Agent initialized, starting main loop...")
        logger.info("Press Ctrl+C to stop")
        agent.run()
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        return 1
    finally:
        # Cleanup
        logger.info("Cleaning up...")
        try:
            mt4.close_connection()
        except Exception:
            pass
        try:
            storage.close()
        except Exception:
            pass
        logger.info("AURUM Trading System Stopped")

    return 0


if __name__ == "__main__":
    sys.exit(main())
