#!/usr/bin/env python3
"""Aurum trading system entry point."""
import logging
import sys
import uuid
from logging.handlers import RotatingFileHandler

from src.mt4.bridge import MT4Bridge, MT4BridgeError
from src.db.storage import SessionStorage
from src.agent.agent import AurumAgent
from src.agent.feedback_logger import FeedbackLogger
from src.agent.session_reporter import generate_report
from src.ui.tui import AurumTUI, TUILogHandler
from src.risk.config import RiskConfig


def _configure_logging(tui: AurumTUI) -> None:
    """File handler + TUI handler; no stdout."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    fh = RotatingFileHandler(
        "logs/aurum.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    fh.setFormatter(logging.Formatter(
        "[%(asctime)s] %(name)s — %(levelname)s — %(message)s"
    ))
    root.addHandler(fh)

    th = TUILogHandler(tui)
    th.setLevel(logging.INFO)
    root.addHandler(th)


def main() -> int:
    tui = AurumTUI()

    with tui:
        _configure_logging(tui)
        logger = logging.getLogger(__name__)

        # ── MT4 connection ────────────────────────────────────────────────
        tui.set_status("Conectando a MT4…")
        try:
            mt4 = MT4Bridge(host="127.0.0.1", port=5555, timeout=5.0)
            mt4.connect()
            if not mt4.ping():
                tui.set_status("Error: MT4 ping falló")
                tui.log("MT4 ping returned False", "ERROR")
                import time; time.sleep(4)
                return 1
            tui.log("MT4 conectado — 127.0.0.1:5555")
        except MT4BridgeError as e:
            tui.set_status("Error: sin conexión MT4")
            tui.log(f"Cannot connect: {e}", "ERROR")
            tui.log("Asegúrate de que AURUM_Bridge EA está activo en MT4", "WARNING")
            import time; time.sleep(6)
            return 1

        # ── Storage ───────────────────────────────────────────────────────
        tui.set_status("Inicializando base de datos…")
        try:
            storage = SessionStorage(db_path="data/aurum.db")
            tui.log("Base de datos lista — data/aurum.db")
        except Exception as e:
            tui.set_status("Error: base de datos")
            tui.log(f"DB init failed: {e}", "ERROR")
            import time; time.sleep(4)
            return 1

        # ── Feedback logger ───────────────────────────────────────────────
        run_id = str(uuid.uuid4())
        flog = FeedbackLogger(run_id=run_id)
        tui.log(f"Sesión iniciada — ID: {run_id[:8]}…")

        # ── Agent ─────────────────────────────────────────────────────────
        tui.set_status("Iniciando agente…")
        try:
            agent = AurumAgent(
                mt4_bridge=mt4,
                storage=storage,
                feedback_logger=flog,
                cycle_interval=900,
                tui=tui,
                risk_config=RiskConfig(),
                run_id=run_id,
            )
            tui.log("Agente inicializado — ciclo: 15 min / 5 min c/ posición")
            agent.run()
        except KeyboardInterrupt:
            tui.set_status("Deteniendo — Ctrl+C")
            logger.info("Shutdown requested by user")
        except Exception as e:
            tui.set_status(f"Error fatal: {str(e)[:60]}")
            logger.error(f"Agent error: {e}", exc_info=True)
            return 1
        finally:
            tui.set_status("Limpiando…")
            try:
                mt4.close_connection()
            except Exception:
                pass
            try:
                storage.close()
            except Exception:
                pass
            try:
                generate_report(run_id, save=True)
                tui.log(f"Reporte guardado — python src/tools/review_session.py {run_id[:8]}")
            except Exception as e:
                logger.warning(f"Could not generate session report: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
