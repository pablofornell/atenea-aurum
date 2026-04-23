# Estructura del Proyecto Aurum

## Directorios

### `/src/` — Código Fuente
- **`agent/`** — Lógica del agente trading (agent.py, prompts.py)
- **`bridge/`** — Integración con Claude (claude_bridge.py) y MT4 (bridge.py)
- **`mt4/`** — Conexión y comunicación con MetaTrader 4
- **`db/`** — Storage y persistencia (storage.py)
- **`strategies/`** — Estrategias de trading (módulos futuros)
- **`tools/`** — Scripts de utilidad y diagnóstico
  - `diagnostic.py` — Diagnóstico del sistema
  - `advanced_diagnostic.py` — Diagnóstico avanzado
  - `cleanup_orders.py` — Limpieza de órdenes
  - `cleanup_all_orders.py` — Limpieza completa
  - `find_lot_size.py` — Cálculo de tamaño de lote
- **`tests/`** — Suite de tests
  - `unit/` — Tests unitarios
  - `integration/` — Tests de integración con MT4

### `/data/` — Datos Persistentes
- `aurum.db` — Base de datos SQLite con historial de sesiones y órdenes

### `/logs/` — Registros
- `aurum.log` — Log de ejecución del sistema

### `/docs/` — Documentación
- `START_HERE.md` — Guía de inicio
- `QUICKSTART.md` — Inicio rápido
- `TESTING.md` — Guía de testing
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
