"""Generate a human+AI readable markdown report from a run's JSONL events.

The output is designed to be fed directly to Claude Code or another agent
as context for suggesting code improvements.
"""
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

LOGS_DIR = Path("logs")
EVENTS_FILE = LOGS_DIR / "aurum_events.jsonl"
SESSIONS_DIR = LOGS_DIR / "sessions"


def load_events(run_id: str) -> list[dict]:
    if not EVENTS_FILE.exists():
        return []
    events = []
    with open(EVENTS_FILE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if record.get("run_id") == run_id:
                    events.append(record)
            except json.JSONDecodeError:
                continue
    return events


def list_runs() -> list[dict]:
    """Return summary of all recorded runs (newest first)."""
    if not EVENTS_FILE.exists():
        return []
    runs: dict[str, dict] = {}
    with open(EVENTS_FILE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = r.get("run_id")
            if not rid:
                continue
            if rid not in runs:
                runs[rid] = {"run_id": rid, "start_ts": r["ts"], "end_ts": r["ts"],
                             "cycles": 0, "events": 0}
            runs[rid]["end_ts"] = r["ts"]
            runs[rid]["events"] += 1
            if r.get("event") == "cycle_start":
                runs[rid]["cycles"] += 1
            if r.get("event") == "run_end":
                runs[rid]["pnl"] = r["data"].get("realised_pnl")
                runs[rid]["duration_s"] = r["data"].get("duration_s")
    return sorted(runs.values(), key=lambda x: x["start_ts"], reverse=True)


def generate_report(run_id: str, save: bool = True) -> str:
    events = load_events(run_id)
    if not events:
        return f"No events found for run_id={run_id}"

    lines = _build_report(run_id, events)
    report = "\n".join(lines)

    if save:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        start_ts = events[0]["ts"].replace(":", "").replace("-", "")[:15]
        fname = SESSIONS_DIR / f"{start_ts}_{run_id[:8]}.md"
        fname.write_text(report, encoding="utf-8")
        print(f"Report saved: {fname}")

    return report


# ------------------------------------------------------------------
# Internal builders
# ------------------------------------------------------------------

def _build_report(run_id: str, events: list[dict]) -> list[str]:
    lines = []

    run_start = _find_first(events, "run_start")
    run_end = _find_first(events, "run_end")

    start_ts = _fmt_ts(events[0]["ts"])
    end_ts = _fmt_ts(events[-1]["ts"])

    lines += [
        f"# AURUM Session Report",
        f"",
        f"- **Run ID**: `{run_id}`",
        f"- **Período**: {start_ts} — {end_ts}",
    ]

    if run_end:
        d = run_end["data"]
        dur = _fmt_duration(d.get("duration_s", 0))
        lines.append(f"- **Duración**: {dur}")
        pnl = d.get("realised_pnl")
        if pnl is not None:
            sign = "+" if pnl >= 0 else ""
            lines.append(f"- **P&L realizado**: {sign}{pnl:.2f} USD")
        sb = d.get("start_balance")
        eb = d.get("end_balance")
        if sb and eb:
            lines.append(f"- **Balance**: {sb:.2f} → {eb:.2f} USD")

    lines.append("")

    # --- Summary stats ---
    lines += ["## Resumen estadístico", ""]
    lines += _build_stats(events)
    lines.append("")

    # --- Cycle detail ---
    lines += ["## Detalle de ciclos", ""]
    lines += _build_cycles(events)
    lines.append("")

    # --- Error analysis ---
    error_events = [e for e in events if e["event"] == "error"]
    if error_events:
        lines += ["## Análisis de errores", ""]
        lines += _build_errors(error_events)
        lines.append("")

    # --- Anomalies ---
    anomalies = _find_anomalies(events)
    if anomalies:
        lines += ["## Anomalías detectadas", ""]
        for a in anomalies:
            lines.append(f"- {a}")
        lines.append("")

    # --- Improvement suggestions (empty, for reviewer) ---
    lines += [
        "## Sugerencias de mejora",
        "",
        "> _Sección para rellenar por el revisor (humano o agente)._",
        "> Añade aquí observaciones, bugs detectados, y propuestas de cambio.",
        "",
        "### Comportamiento del agente",
        "",
        "- [ ] ",
        "",
        "### Gestión de riesgo",
        "",
        "- [ ] ",
        "",
        "### Infraestructura / conexión",
        "",
        "- [ ] ",
        "",
        "### Calidad del prompt / razonamiento de Claude",
        "",
        "- [ ] ",
        "",
    ]

    # --- Code references ---
    lines += _build_code_refs(events)

    return lines


def _build_stats(events: list[dict]) -> list[str]:
    action_counts: Counter = Counter()
    error_counts: Counter = Counter()
    total_cycles = 0
    cycle_durations = []

    for e in events:
        if e["event"] == "cycle_start":
            total_cycles += 1
        elif e["event"] == "claude_decision":
            action_counts[e["data"].get("action_type", "?")] += 1
        elif e["event"] == "error":
            error_counts[e["data"].get("type", "?")] += 1
        elif e["event"] == "cycle_end":
            d = e["data"].get("duration_s")
            if d:
                cycle_durations.append(d)

    lines = [f"- **Ciclos totales**: {total_cycles}"]

    if action_counts:
        breakdown = ", ".join(f"{k}×{v}" for k, v in action_counts.most_common())
        lines.append(f"- **Decisiones Claude**: {breakdown}")

    if error_counts:
        err_breakdown = ", ".join(f"{k}×{v}" for k, v in error_counts.most_common())
        lines.append(f"- **Errores**: {err_breakdown}")
    else:
        lines.append("- **Errores**: ninguno")

    if cycle_durations:
        avg = sum(cycle_durations) / len(cycle_durations)
        lines.append(f"- **Duración media de ciclo**: {avg:.1f}s")

    reconnects = [e for e in events if e["event"] == "reconnect"]
    if reconnects:
        ok = sum(1 for r in reconnects if r["data"].get("success"))
        lines.append(f"- **Reconexiones**: {len(reconnects)} ({ok} exitosas)")

    return lines


def _build_cycles(events: list[dict]) -> list[str]:
    # Group events by session_id, preserving order
    sessions: dict[str, list[dict]] = defaultdict(list)
    order = []
    for e in events:
        sid = e.get("session_id")
        if sid:
            if sid not in sessions:
                order.append(sid)
            sessions[sid].append(e)

    lines = []
    for sid in order:
        evs = sessions[sid]
        ts = _fmt_ts(evs[0]["ts"], short=True)
        lines.append(f"### {ts} — ciclo `{sid[:8]}`")
        lines.append("")

        ctx = _find_first(evs, "market_context")
        if ctx:
            d = ctx["data"]
            price = d.get("price")
            account = d.get("account")
            positions = d.get("positions", [])
            conn = d.get("connection_ok", True)

            if not conn:
                lines.append("⚠️ **Sin datos de mercado** (conexión perdida al inicio del ciclo)")
            else:
                if price:
                    lines.append(f"**Precio**: bid={price['bid']:.2f} ask={price['ask']:.2f} spread={price.get('spread', 0):.2f}")
                if account:
                    lines.append(f"**Cuenta**: balance={account['balance']:.2f} equity={account['equity']:.2f}")
                if positions:
                    for p in positions:
                        lines.append(
                            f"**Posición abierta**: #{p['ticket']} {p['type']} {p['lots']} lot "
                            f"@ {p['open_price']:.2f} | SL={p['sl']:.2f} TP={p['tp']:.2f} P&L={p['profit']:+.2f}"
                        )
                else:
                    lines.append("**Posiciones**: ninguna")
            lines.append("")

        decisions = [e for e in evs if e["event"] == "claude_decision"]
        for dec in decisions:
            d = dec["data"]
            action = d.get("action_type", "?")
            reasoning = d.get("reasoning", "").strip()
            elapsed = d.get("claude_elapsed_s", "?")
            params = d.get("params", {})

            lines.append(f"**Decisión Claude**: `{action}` ({elapsed}s)")
            if params:
                param_str = " | ".join(f"{k}={v}" for k, v in params.items() if v)
                lines.append(f"Parámetros: {param_str}")
            if reasoning:
                lines.append(f"> {reasoning[:400]}")
            lines.append("")

        results = [e for e in evs if e["event"] == "action_result"]
        for res in results:
            d = res["data"]
            ok = d.get("ok", False)
            status = "✓" if ok else "✗"
            detail_parts = [f"{k}={v}" for k, v in d.items() if k not in ("action", "ok")]
            detail = " ".join(detail_parts)
            lines.append(f"**Resultado**: {status} {detail}")
            lines.append("")

        errors = [e for e in evs if e["event"] == "error"]
        for err in errors:
            d = err["data"]
            lines.append(f"**Error** `{d.get('type')}`: {d.get('detail')}")
            lines.append("")

        end = _find_first(evs, "cycle_end")
        if end:
            dur = end["data"].get("duration_s", "?")
            lines.append(f"_Duración del ciclo: {dur}s_")
            lines.append("")

        lines.append("---")
        lines.append("")

    return lines


def _build_errors(error_events: list[dict]) -> list[str]:
    by_type: defaultdict = defaultdict(list)
    for e in error_events:
        by_type[e["data"].get("type", "unknown")].append(e)

    lines = []
    for etype, evs in by_type.items():
        lines.append(f"### `{etype}` ({len(evs)} ocurrencias)")
        lines.append("")
        for e in evs:
            ts = _fmt_ts(e["ts"], short=True)
            detail = e["data"].get("detail", "")
            sid = e.get("session_id", "")[:8] if e.get("session_id") else "—"
            lines.append(f"- `{ts}` ciclo `{sid}`: {detail}")
        lines.append("")
    return lines


def _find_anomalies(events: list[dict]) -> list[str]:
    anomalies = []

    # SELL/BUY attempted when get_positions returned []  but connection was lost
    for e in events:
        if e["event"] == "action_result" and e["data"].get("action") in ("SELL", "BUY"):
            if not e["data"].get("ok"):
                sid = e.get("session_id")
                ctx_event = next(
                    (x for x in events
                     if x.get("session_id") == sid and x["event"] == "market_context"),
                    None
                )
                if ctx_event and not ctx_event["data"].get("connection_ok"):
                    ts = _fmt_ts(e["ts"], short=True)
                    anomalies.append(
                        f"`{ts}` — Orden {e['data']['action']} intentada sin datos de mercado (conexión caída)."
                    )

    # Consecutive errors of the same type
    error_types = [e["data"].get("type") for e in events if e["event"] == "error"]
    for i in range(len(error_types) - 2):
        if error_types[i] == error_types[i+1] == error_types[i+2]:
            anomalies.append(
                f"Error `{error_types[i]}` ocurrió 3+ veces consecutivas — posible bucle sin recuperación."
            )
            break

    # Claude timeout
    timeouts = [e for e in events if e["event"] == "error" and e["data"].get("type") == "timeout"]
    if timeouts:
        anomalies.append(f"Claude CLI tardó demasiado ({len(timeouts)} timeout(s)) — revisar carga del sistema o aumentar timeout.")

    return list(dict.fromkeys(anomalies))  # deduplicate preserving order


def _build_code_refs(events: list[dict]) -> list[str]:
    """Point reviewers to the relevant source files for each error type."""
    error_types = {e["data"].get("type") for e in events if e["event"] == "error"}
    has_reconnect = any(e["event"] == "reconnect" for e in events)

    lines = ["## Referencias de código para el revisor", ""]
    lines.append("Ficheros relevantes según los eventos de esta sesión:")
    lines.append("")
    lines.append("| Fichero | Relevancia |")
    lines.append("|---------|------------|")
    lines.append("| `src/agent/agent.py` | Lógica principal del ciclo, decisiones, guardia anti-duplicados |")
    lines.append("| `src/agent/prompts.py` | System prompt enviado a Claude — calidad del razonamiento |")
    lines.append("| `src/bridge/claude_bridge.py` | Timeout, parsing de respuesta, subprocess |")
    lines.append("| `src/mt4/bridge.py` | Conexión TCP, reconexión, `set_timeframe`, `modify` |")
    lines.append("| `ops/AURUM_Bridge.mq4` | EA MT4 — errores de MODIFY/CLOSE/ORDER |")

    if "modify_failed" in error_types:
        lines.append("| `src/mt4/bridge.py:get_stop_level` | Stop level del broker — causa de modify_failed |")
    if has_reconnect or "connection" in error_types:
        lines.append("| `src/mt4/bridge.py:reconnect` | Lógica de reconexión tras CHANGE_TIMEFRAME |")
    if "timeout" in error_types:
        lines.append("| `src/bridge/claude_bridge.py:60` | Timeout de Claude CLI (actualmente 120s) |")

    lines.append("")
    return lines


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _find_first(events: list[dict], event_type: str) -> Optional[dict]:
    return next((e for e in events if e["event"] == event_type), None)


def _fmt_ts(iso: str, short: bool = False) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if short:
            return dt.strftime("%H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return iso


def _fmt_duration(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {sec}s"
    if m:
        return f"{m}m {sec}s"
    return f"{sec}s"
