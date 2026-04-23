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

## Directorios

### Workspaces
- **`/src`** — Código fuente
  - `agent/` — Lógica del agente trading
  - `bridge/` — Integración Claude y MT4
  - `mt4/` — Conexión MetaTrader 4
  - `db/` — Persistencia (SQLite)
  - `strategies/` — Estrategias trading
  - `tools/` — Scripts de utilidad y diagnóstico
  - `tests/` — Suite de tests (unit/ e integration/)
- **`/docs`** — Documentación (guías, testing, estructura)
- **`/ops`** — EA, instalación, despliegue MT4
- **`/planning`** — Specs y decisiones arquitectónicas
- **`/data`** — Datos persistentes (aurum.db)
- **`/logs`** — Archivos de log del sistema

## Routing
| Tarea | Carpeta | Leer | Notas |
|-------|---------|------|-------|
| Especificar feature | `/planning` | — | Usar: `feature-name_spec.md` |
| Escribir código | `/src` | — | Modular por componente (agent, bridge, mt4, etc) |
| Agregar/editar tests | `/src/tests` | — | Seguir: `test_*.py`, `/integration/` para MT4 |
| Scripts de diagnóstico | `/src/tools` | — | Para debugging y utilidades |
| Documentar | `/docs` | `PROJECT_STRUCTURE.md` | Guías de setup, testing, arquitectura |
| Desplegar/depurar MT4 | `/ops` | `README.md` | Instalación EA, troubleshooting |
| Decision records | `/planning` | — | Usar: `DD-MM-YYYY-decision.md` |

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
