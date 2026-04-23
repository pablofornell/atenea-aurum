# Estructura del Proyecto Aurum

## Directorios

### `/src/` — Código Fuente

- **`agent/`** — Lógica del agente trading
  - `agent.py` — `AurumAgent`: orquestador principal del ciclo de trading
  - `prompts.py` — System prompt SMC inyectado en cada llamada a Claude
  - `filters.py` — `EntryFilters`: bloquea sesiones Asia/Late NY, ATR<8, spread>30
  - `memory.py` — `CycleMemory`: inyecta historial de decisiones recientes en el prompt
  - `feedback_logger.py` — `FeedbackLogger`: eventos JSONL append-only por run
  - `session_reporter.py` — `SessionReporter`: genera informe markdown desde el JSONL
- **`bridge/`** — Integración con Claude CLI y MT4
  - `claude_bridge.py` — Llama a Claude Code CLI via subprocess (stdin, cwd=strategy/)
- **`mt4/`** — Conexión y comunicación con MetaTrader 4
  - `bridge.py` — `MT4Bridge`: cliente TCP 127.0.0.1:5555 ↔ EA MQ4
  - `screenshot.py` — Captura de pantalla de la ventana MT4
- **`db/`** — Storage y persistencia
  - `storage.py` — `SessionStorage`: tablas `sessions`, `orders`, `cycle_decisions` (SQLite)
- **`risk/`** — Módulo de gestión de riesgo
  - `config.py` — `RiskConfig`: dataclass con todos los parámetros de riesgo
  - `validator.py` — `OrderValidator`: valida SL/TP/lots/R:R antes de enviar a MT4
  - `circuit_breaker.py` — `CircuitBreaker`: halt si 3% drawdown diario o 3 pérdidas seguidas
  - `position_sizer.py` — `calculate_lots`: 1% de balance, techo en `max_lots` (0.50)
  - `trade_manager.py` — `TradeManager`: breakeven automático a 1R, trailing a 2R
- **`ui/`** — Interfaz de terminal
  - `tui.py` — `AurumTUI`: dashboard rich en tiempo real (live layout, panels, log)
- **`strategies/`** — Estrategias de trading (reservado para expansión futura)
- **`tools/`** — Scripts de utilidad y diagnóstico
  - `diagnostic.py` — Diagnóstico básico del sistema
  - `advanced_diagnostic.py` — Diagnóstico avanzado
  - `cleanup_orders.py` — Limpieza de órdenes (tickets dinámicos)
  - `cleanup_all_orders.py` — Limpieza completa de todas las órdenes
  - `find_lot_size.py` — Cálculo manual de tamaño de lote
  - `review_session.py` — CLI para revisar sesiones y generar prompts de mejora
- **`tests/`** — Suite de tests
  - `unit/` — Tests unitarios (sin dependencia de MT4)
  - `integration/` — Tests de integración con MT4 real

### `/data/` — Datos Persistentes
- `aurum.db` — Base de datos SQLite con historial de sesiones y órdenes

### `/logs/` — Registros
- `aurum.log` — Log operacional en tiempo real (Python logging)
- `aurum_events.jsonl` — Eventos estructurados JSON para el feedback loop (append-only)
- `sessions/` — Informes markdown por sesión, generados automáticamente al parar el sistema

### `/docs/` — Documentación
- `START_HERE.md` — Guía de inicio
- `QUICKSTART.md` — Inicio rápido
- `TESTING.md` — Guía de testing
- `LOGGING.md` — Sistema de logging y ciclo de feedback
- `PROJECT_STRUCTURE.md` — Esta documentación

### `/ops/` — Despliegue y Operaciones MT4
- `AURUM_Bridge.mq4` — Expert Advisor para MT4
- `install_ea.ps1` — Script de instalación automatizada
- `socket-library-mt4-mt5.mqh` — Librería de sockets
- `README.md` — Instrucciones de instalación

### `/planning/` — Especificaciones y Decisiones
- Almacena specs de features, ADRs (Architecture Decision Records)
- Sigue patrón: `feature-name_spec.md` o `DD-MM-YYYY-decision-title.md`

## Archivos en Raíz

- **`aurum.py`** — Entry point del sistema (inicia agente, conecta MT4, storage)
- **`setup.py`** — Instalación de dependencias
- **`CLAUDE.md`** — Instrucciones del proyecto (cargadas automáticamente por Claude Code)

## Configuración

- **`.gitignore`** — Excluye `__pycache__/`, `*.db`, `logs/`, `venv/`, etc.
- **`requirements.txt`** — Dependencias del proyecto

## Ejecución

```bash
# Entrada principal
python aurum.py

# Tests
pytest src/tests/
pytest src/tests/integration/ -m mt4
```
