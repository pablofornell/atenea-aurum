# Aurum — Developer Context

Aurum es un sistema de trading agéntico basado en LLM para operar XAUUSD (Gold/USD).

## Tu rol aquí

Cuando trabajas en este repositorio **no eres el agente AURUM**. Eres el ingeniero que desarrolla y mantiene su evolución y retroalimentación.

El agente AURUM es una instancia separada de Claude Code CLI, lanzada por subprocess desde `src/bridge/claude_bridge.py` con `cwd=strategy/`. Esa instancia carga `strategy/CLAUDE.md` como identidad y recibe el system prompt de `src/agent/prompts.py`.

Tu trabajo en este repo es:
- Desarrollar y mantener el código del sistema (`src/`, `ops/`)
- Revisar logs de sesión (`logs/sessions/`) y sacar conclusiones
- Mejorar los prompts del agente (`src/agent/prompts.py`, `strategy/CLAUDE.md`)
- Escribir y mantener tests (`src/tests/`)
- Tomar decisiones arquitectónicas (`planning/`)

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
    input=prompt, capture_output=True, text=True, cwd=STRATEGY_DIR  # strategy/
)
```

El prompt se pasa por **stdin** para evitar el límite de caracteres de la terminal. `cwd=STRATEGY_DIR` hace que la instancia agente cargue `strategy/CLAUDE.md` como su identidad. No hay API key ni SDK de Anthropic.

## Directorios

### Workspaces
- **`/src`** — Código fuente
  - `agent/` — Lógica del agente trading
    - `agent.py` — Orquestador principal del ciclo de trading
    - `prompts.py` — System prompt SMC para la instancia Claude agente
    - `filters.py` — `EntryFilters`: bloquea Asia/Late NY, ATR<8, spread>30
    - `memory.py` — `CycleMemory`: inyecta historial de decisiones en el prompt
    - `feedback_logger.py` — `FeedbackLogger`: escribe eventos JSONL append-only
    - `session_reporter.py` — `SessionReporter`: genera informes markdown por sesión
  - `bridge/` — Integración Claude y MT4
    - `claude_bridge.py` — Llama a Claude Code CLI via subprocess con stdin
  - `mt4/` — Conexión MetaTrader 4
    - `bridge.py` — `MT4Bridge`: TCP socket 127.0.0.1:5555 ↔ EA
    - `screenshot.py` — Captura de pantalla de la ventana MT4
  - `db/` — Persistencia (SQLite)
    - `storage.py` — `SessionStorage`: tablas `sessions`, `orders`, `cycle_decisions`
  - `risk/` — Gestión de riesgo (validación, circuit breaker, sizing)
    - `config.py` — `RiskConfig`: parámetros centralizados (dataclass)
    - `validator.py` — `OrderValidator`: valida SL/TP/lots/R:R antes de enviar a MT4
    - `circuit_breaker.py` — `CircuitBreaker`: halt si 3% drawdown o 3 pérdidas consecutivas
    - `position_sizer.py` — `calculate_lots`: sizing al 1% de balance, máx 0.50 lotes
    - `trade_manager.py` — `TradeManager`: breakeven a 1R, trailing a 2R
  - `ui/` — Interfaz de terminal
    - `tui.py` — `AurumTUI`: dashboard rich en tiempo real (live layout)
  - `strategies/` — Módulos de estrategia (reservado para expansión futura)
  - `tools/` — Scripts de utilidad y diagnóstico
    - `diagnostic.py` — Diagnóstico básico del sistema
    - `advanced_diagnostic.py` — Diagnóstico avanzado
    - `cleanup_orders.py` / `cleanup_all_orders.py` — Limpieza de órdenes MT4
    - `find_lot_size.py` — Cálculo manual de tamaño de lote
    - `review_session.py` — CLI para revisar sesiones y generar prompts de mejora
  - `tests/` — Suite de tests
    - `unit/` — Tests unitarios (no requieren MT4)
    - `integration/` — Tests de integración con MT4 real
- **`/docs`** — Documentación (guías, testing, estructura, logging)
- **`/ops`** — EA, instalación, despliegue MT4
- **`/planning`** — Specs y decisiones arquitectónicas
- **`/data`** — Datos persistentes (aurum.db)
- **`/logs`** — Archivos de log del sistema
  - `aurum.log` — Log operacional Python (RotatingFileHandler)
  - `aurum_events.jsonl` — Eventos estructurados JSON, append-only por run
  - `sessions/` — Informes markdown por sesión (`<ts>_<runid>.md`)

## Routing
| Tarea | Carpeta | Leer | Notas |
|-------|---------|------|-------|
| Especificar feature | `/planning` | — | Usar: `feature-name_spec.md` |
| Orquestación del agente | `src/agent/agent.py` | — | Punto de entrada del ciclo trading |
| Prompts / identidad SMC | `src/agent/prompts.py`, `strategy/CLAUDE.md` | — | Dos capas: system prompt + identidad agente |
| Filtros de entrada | `src/agent/filters.py` | — | Sesión, ATR, spread — modificar con cuidado |
| Memoria entre ciclos | `src/agent/memory.py` | `src/db/storage.py` | Lee `cycle_decisions` de SQLite |
| Parámetros de riesgo | `src/risk/config.py` | — | `RiskConfig` — cambiar aquí, aplica a todo |
| Validación de órdenes | `src/risk/validator.py` | `src/risk/config.py` | SL mínimo, R:R, lots máx |
| Circuit breaker | `src/risk/circuit_breaker.py` | `src/risk/config.py` | Drawdown diario / pérdidas consecutivas |
| Sizing de posición | `src/risk/position_sizer.py` | — | 1% balance, techo en `max_lots` |
| Gestión de posición | `src/risk/trade_manager.py` | — | Breakeven + trailing automático |
| Puente Claude CLI | `src/bridge/claude_bridge.py` | — | stdin, cwd=strategy/, timeout 120s |
| Conexión MT4 | `src/mt4/bridge.py` | — | TCP 127.0.0.1:5555, protocol texto |
| Feedback / eventos | `src/agent/feedback_logger.py` | `docs/LOGGING.md` | JSONL append-only, no bloquea el agente |
| Informes de sesión | `src/agent/session_reporter.py` | `docs/LOGGING.md` | Genera markdown desde JSONL |
| Revisión de sesión | `src/tools/review_session.py` | `docs/LOGGING.md` | CLI: `latest`, `--prompt`, `--save` |
| Dashboard TUI | `src/ui/tui.py` | — | Requiere `rich`; opcional (se pasa como parámetro) |
| Agregar/editar tests | `src/tests/` | `docs/TESTING.md` | `test_*.py`; `/integration/` requiere MT4 |
| Scripts de diagnóstico | `src/tools/` | — | Para debugging sin MT4 activo |
| Documentar | `/docs` | `PROJECT_STRUCTURE.md` | Guías de setup, testing, arquitectura |
| Desplegar/depurar MT4 | `/ops` | `README.md` | Instalación EA, troubleshooting |
| Decision records | `/planning` | — | Usar: `DD-MM-YYYY-decision-title.md` |

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
