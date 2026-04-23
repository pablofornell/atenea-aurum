"""CLI tool to review Aurum sessions and generate improvement prompts.

Usage:
    python src/tools/review_session.py                    # list all recorded runs
    python src/tools/review_session.py latest             # report of the latest run
    python src/tools/review_session.py <run_id_prefix>    # report of a specific run
    python src/tools/review_session.py latest --prompt    # print reviewer prompt for Claude
    python src/tools/review_session.py latest --save      # force save report to disk
"""
import argparse
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.agent.session_reporter import generate_report, list_runs, SESSIONS_DIR

SOURCE_FILES = [
    "src/agent/agent.py",
    "src/agent/prompts.py",
    "src/bridge/claude_bridge.py",
    "src/mt4/bridge.py",
    "ops/AURUM_Bridge.mq4",
]

REVIEWER_PROMPT_TEMPLATE = """\
Eres un agente de programación senior revisando el sistema de trading automático AURUM.

A continuación encontrarás:
1. El informe detallado de una sesión de trading real (lo que hizo el agente, sus decisiones, errores y anomalías).
2. El código fuente de los ficheros clave del sistema.

Tu tarea es:
- Analizar el informe e identificar bugs, comportamientos subóptimos, y oportunidades de mejora.
- Para cada mejora, proponer un cambio concreto en el código (fichero, función, qué cambiar y por qué).
- Priorizar por impacto: primero los que afecten a la integridad de las operaciones, luego los de rendimiento, luego los de calidad.
- Si detectas patrones en el razonamiento de Claude (system prompt) que produzcan malas decisiones, propón cambios al prompt.

Sé específico: "en `src/agent/agent.py` línea X, cambia Y por Z porque..."

---

{report}

---

## Código fuente relevante

{source_code}

---

Empieza tu análisis ahora.
"""


def cmd_list():
    runs = list_runs()
    if not runs:
        print("No hay sesiones registradas todavía.")
        print("Ejecuta aurum.py para empezar a grabar eventos.")
        return

    print(f"{'RUN ID':<12} {'INICIO':<22} {'DURACIÓN':<12} {'CICLOS':<8} {'P&L':>10}")
    print("-" * 70)
    for r in runs:
        rid = r["run_id"][:12]
        ts = r["start_ts"][:19].replace("T", " ")
        dur = _fmt_dur(r.get("duration_s"))
        cycles = r.get("cycles", "?")
        pnl = r.get("pnl")
        pnl_str = f"{'+' if pnl and pnl >= 0 else ''}{pnl:.2f}" if pnl is not None else "—"
        print(f"{rid:<12} {ts:<22} {dur:<12} {str(cycles):<8} {pnl_str:>10}")


def cmd_report(run_id: str, save: bool = False) -> str:
    report = generate_report(run_id, save=save)
    print(report)
    return report


def cmd_prompt(run_id: str, save: bool = False):
    report = generate_report(run_id, save=save)

    # Load source code (truncated to avoid huge prompts)
    source_parts = []
    for rel_path in SOURCE_FILES:
        p = Path(rel_path)
        if p.exists():
            content = p.read_text(encoding="utf-8")
            # Truncate very large files
            if len(content) > 6000:
                content = content[:6000] + f"\n... [truncated, full file at {rel_path}]"
            source_parts.append(f"### `{rel_path}`\n\n```python\n{content}\n```")

    source_code = "\n\n".join(source_parts)
    prompt = REVIEWER_PROMPT_TEMPLATE.format(report=report, source_code=source_code)

    print(prompt)

    # Also save to disk so it can be piped to claude CLI
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    prompt_file = SESSIONS_DIR / f"{run_id[:8]}_review_prompt.txt"
    prompt_file.write_text(prompt, encoding="utf-8")
    print(f"\n---\nPrompt guardado en: {prompt_file}", file=sys.stderr)
    print(f"Para pasárselo a Claude: cat {prompt_file} | claude --dangerously-skip-permissions", file=sys.stderr)


def _resolve_run_id(arg: str) -> Optional[str]:
    runs = list_runs()
    if not runs:
        return None
    if arg == "latest":
        return runs[0]["run_id"]
    # prefix match
    matches = [r["run_id"] for r in runs if r["run_id"].startswith(arg)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Prefijo ambiguo: {arg} coincide con {len(matches)} runs. Sé más específico.")
        return None
    print(f"No se encontró ningún run con prefijo: {arg}")
    return None


def _fmt_dur(seconds) -> str:
    if seconds is None:
        return "—"
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m{sec:02d}s"


from typing import Optional


def main():
    parser = argparse.ArgumentParser(description="AURUM session reviewer")
    parser.add_argument("run", nargs="?", default=None,
                        help="Run ID prefix or 'latest'. Omit to list all runs.")
    parser.add_argument("--prompt", action="store_true",
                        help="Generate full reviewer prompt (report + source code) for Claude")
    parser.add_argument("--save", action="store_true",
                        help="Save report to logs/sessions/")
    args = parser.parse_args()

    if args.run is None:
        cmd_list()
        return

    run_id = _resolve_run_id(args.run)
    if run_id is None:
        sys.exit(1)

    if args.prompt:
        cmd_prompt(run_id, save=args.save)
    else:
        cmd_report(run_id, save=args.save)


if __name__ == "__main__":
    main()
