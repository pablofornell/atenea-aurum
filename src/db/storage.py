"""SQLite storage for trading sessions, orders, and analysis history."""
import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class StorageError(Exception):
    """Database operation failed."""
    pass


class SessionStorage:
    """SQLite storage for Aurum trading sessions and orders."""

    def __init__(self, db_path: str = "data/aurum.db"):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self):
        """Initialize database tables if they don't exist."""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
            cursor = self.conn.cursor()

            # Session turns (conversation history)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT,
                    screenshot_path TEXT,
                    timeframe TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Order log
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS order_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    symbol TEXT,
                    lots REAL,
                    sl REAL,
                    tp REAL,
                    ticket INTEGER,
                    result TEXT,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Cycle log (high-level trading cycles)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cycle_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timeframe TEXT,
                    screenshot_path TEXT,
                    claude_response TEXT,
                    duration_ms INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Cycle-level decision memory (persists across cycles for context injection)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cycle_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    cycle_num INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    reasoning TEXT,
                    price REAL,
                    sl REAL,
                    tp REAL,
                    lots REAL,
                    atr REAL,
                    session_name TEXT,
                    pnl_at_decision REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    session_date TEXT NOT NULL,
                    pnl REAL,
                    trades_taken INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0,
                    key_errors TEXT,
                    lesson TEXT NOT NULL,
                    raw_events_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategy_insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    insight TEXT NOT NULL,
                    confidence INTEGER DEFAULT 3,
                    source_sessions TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            self.conn.commit()
            logger.info(f"Database initialized: {self.db_path}")
        except sqlite3.Error as e:
            raise StorageError(f"Failed to initialize database: {e}")

    def save_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        screenshot_path: Optional[str] = None,
        timeframe: Optional[str] = None
    ):
        """Save a conversation turn (user or assistant).

        Args:
            session_id: Session identifier
            role: "user" or "assistant"
            content: Turn content (text/JSON)
            screenshot_path: Path to screenshot if applicable
            timeframe: Chart timeframe (e.g., "H1", "M5")
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO session_turns (session_id, role, content, screenshot_path, timeframe)
                VALUES (?, ?, ?, ?, ?)
            """, (session_id, role, content, screenshot_path, timeframe))
            self.conn.commit()
            logger.debug(f"Saved turn for session {session_id} (role={role})")
        except sqlite3.Error as e:
            raise StorageError(f"Failed to save turn: {e}")

    def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all turns for a session in order.

        Args:
            session_id: Session identifier

        Returns:
            List of turns with schema: {id, session_id, role, content, screenshot_path, timeframe, created_at}
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, session_id, role, content, screenshot_path, timeframe, created_at
                FROM session_turns
                WHERE session_id = ?
                ORDER BY created_at ASC
            """, (session_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            raise StorageError(f"Failed to fetch session history: {e}")

    def clear_session(self, session_id: str):
        """Delete all turns for a session.

        Args:
            session_id: Session identifier
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM session_turns WHERE session_id = ?", (session_id,))
            self.conn.commit()
            logger.debug(f"Cleared session {session_id}")
        except sqlite3.Error as e:
            raise StorageError(f"Failed to clear session: {e}")

    def log_order(
        self,
        session_id: str,
        action: str,
        symbol: str,
        lots: float,
        sl: float,
        tp: float,
        ticket: Optional[int] = None,
        result: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """Log a trading order (open, close, modify).

        Args:
            session_id: Session identifier
            action: "BUY", "SELL", "CLOSE", "MODIFY"
            symbol: Trading instrument (e.g., "XAUUSD")
            lots: Order size
            sl: Stop loss price
            tp: Take profit price
            ticket: MT4 order ticket (if successful)
            result: "OK" or error code
            error_message: Error details if failed
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO order_log
                (session_id, action, symbol, lots, sl, tp, ticket, result, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (session_id, action, symbol, lots, sl, tp, ticket, result, error_message))
            self.conn.commit()
            logger.debug(f"Logged order: {action} {symbol} {lots}lot (session={session_id})")
        except sqlite3.Error as e:
            raise StorageError(f"Failed to log order: {e}")

    def log_cycle(
        self,
        session_id: str,
        timeframe: str,
        claude_response: str,
        duration_ms: Optional[int] = None,
        screenshot_path: Optional[str] = None,
    ):
        """Log a high-level trading cycle.

        Args:
            session_id: Session identifier
            timeframe: Chart timeframe analyzed
            claude_response: Raw JSON response from Claude
            duration_ms: Cycle duration in milliseconds
            screenshot_path: Deprecated, kept for DB compatibility
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO cycle_log (session_id, timeframe, screenshot_path, claude_response, duration_ms)
                VALUES (?, ?, ?, ?, ?)
            """, (session_id, timeframe, screenshot_path, claude_response, duration_ms))
            self.conn.commit()
            logger.debug(f"Logged cycle: {timeframe} (session={session_id})")
        except sqlite3.Error as e:
            raise StorageError(f"Failed to log cycle: {e}")

    def get_order_log(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all orders for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of orders
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM order_log
                WHERE session_id = ?
                ORDER BY created_at ASC
            """, (session_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            raise StorageError(f"Failed to fetch order log: {e}")

    def save_cycle_decision(
        self,
        run_id: str,
        session_id: str,
        cycle_num: int,
        action: str,
        reasoning: str = "",
        price: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        lots: Optional[float] = None,
        atr: Optional[float] = None,
        session_name: str = "",
        pnl_at_decision: Optional[float] = None,
    ) -> None:
        """Persist a cycle decision for cross-cycle memory injection."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO cycle_decisions
                (run_id, session_id, cycle_num, action, reasoning, price, sl, tp, lots, atr, session_name, pnl_at_decision)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (run_id, session_id, cycle_num, action, reasoning, price, sl, tp, lots, atr, session_name, pnl_at_decision))
            self.conn.commit()
        except sqlite3.Error as e:
            raise StorageError(f"Failed to save cycle decision: {e}")

    def get_recent_cycle_decisions(self, run_id: str, n: int = 5) -> List[Dict[str, Any]]:
        """Retrieve the most recent N cycle decisions for this run (cross-cycle memory)."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT cycle_num, action, reasoning, price, sl, tp, lots, atr, session_name, pnl_at_decision, created_at
                FROM cycle_decisions
                WHERE run_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (run_id, n))
            rows = cursor.fetchall()
            result = [dict(row) for row in rows]
            result.reverse()  # chronological order for prompt injection
            return result
        except sqlite3.Error as e:
            raise StorageError(f"Failed to fetch cycle decisions: {e}")

    def save_session_summary(
        self,
        run_id: str,
        session_date: str,
        pnl: Optional[float],
        trades_taken: int,
        wins: int,
        losses: int,
        key_errors: str,
        lesson: str,
        raw_events_json: Optional[str] = None,
    ) -> int:
        """Insert a session summary and return the inserted row id."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO session_summaries
                (run_id, session_date, pnl, trades_taken, wins, losses, key_errors, lesson, raw_events_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (run_id, session_date, pnl, trades_taken, wins, losses, key_errors, lesson, raw_events_json))
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            raise StorageError(f"Failed to save session summary: {e}")

    def get_session_summaries(self, n: int = 14) -> List[Dict[str, Any]]:
        """Return the last N session summaries ordered by created_at DESC."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM session_summaries
                ORDER BY created_at DESC
                LIMIT ?
            """, (n,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            raise StorageError(f"Failed to fetch session summaries: {e}")

    def get_all_session_summaries(self) -> List[Dict[str, Any]]:
        """Return all session summaries ordered by session_date ASC."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM session_summaries
                ORDER BY session_date ASC
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            raise StorageError(f"Failed to fetch all session summaries: {e}")

    def save_strategy_insights(self, insights: List[Dict[str, Any]]) -> None:
        """Replace all strategy insights with the provided list (DELETE + INSERT in transaction)."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM strategy_insights")
            for item in insights:
                cursor.execute("""
                    INSERT INTO strategy_insights (insight, confidence, source_sessions)
                    VALUES (?, ?, ?)
                """, (item["insight"], item.get("confidence", 3), item.get("source_sessions")))
            self.conn.commit()
        except sqlite3.Error as e:
            self.conn.rollback()
            raise StorageError(f"Failed to save strategy insights: {e}")

    def get_strategy_insights(self) -> List[Dict[str, Any]]:
        """Return all strategy insights ordered by confidence DESC, created_at DESC."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, insight, confidence, source_sessions, created_at, last_updated
                FROM strategy_insights
                ORDER BY confidence DESC, created_at DESC
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            raise StorageError(f"Failed to fetch strategy insights: {e}")

    def close(self):
        """Close database connection."""
        if self.conn:
            try:
                self.conn.close()
                logger.debug("Database connection closed")
            except Exception as e:
                logger.warning(f"Error closing database: {e}")
            finally:
                self.conn = None

    def __enter__(self):
        """Context manager support."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager support."""
        self.close()
