# Aurum

Aurum — Agentic Trading System basado en LLM para operar XAUUSD (Gold/USD)

## Tech Stack
- Frontend: Windows Terminal (CLI)
- Backend: Python + Claude Code CLI (via subprocess)
- Database: SQLite (local, para logs de señales y operaciones)
- Deploy: MT4 (MetaTrader 4)

## Architecture

El agente llama a Claude Code CLI mediante subprocess, no usa el SDK de Anthropic directamente:

```python
subprocess.run(
    ["claude", "--dangerously-skip-permissions", "--output-format", "json"],
    input=prompt, capture_output=True, text=True, cwd=REPO_DIR
)
```

El prompt se pasa por **stdin** (no como argumento `-p`) para evitar el límite de caracteres de la terminal. `cwd=REPO_DIR` hace que Claude Code cargue este `CLAUDE.md` como identidad AURUM automáticamente. No hay API key ni SDK de Anthropic.

## Workspaces
- /planning — Specs, arquitectura, decisiones
- /src — Código fuente (agente, bridge, estrategias)
- /docs — Documentación
- /ops — Despliegue y operaciones MT4

## Routing
| Tarea | Ir a | Leer | Skills |
|-------|-------|------|--------|
| Especificar una feature | /planning | CONTEXT.md | — |
| Escribir código | /src | CONTEXT.md | — |
| Documentar | /docs | CONTEXT.md | — |
| Desplegar o depurar | /ops | CONTEXT.md | — |

## Testing
- Framework: `pytest`
- Tests de integración con MT4: verifican que las órdenes se ejecutan correctamente en la plataforma
- Ejecutar tests: `pytest src/tests/`
- Ejecutar tests de integración MT4: `pytest src/tests/integration/ -m mt4`

## Naming conventions
- Specs: `feature-name_spec.md`
- Módulos Python: `snake_case.py`
- Tests unitarios: `test_feature_name.py`
- Tests de integración MT4: `test_mt4_feature_name.py`
- Decision records: `DD-MM-YYYY-decision-title.md`
