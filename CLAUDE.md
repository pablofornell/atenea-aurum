# AURUM

Bot de trading algorítmico para Gold/XAUUSD. Corre ciclos cada ~15 min: recoge datos de MT4, consulta a Claude como agente, ejecuta la decisión via risk manager.

**Desarrollador:** Pablo Fornell — pablo.fornell.perinan@gmail.com

## Stack

- Python 3.13, textual (TUI), rich
- Claude API invocado como subproceso (`agent/caller.py` llama `claude` CLI)
- MT4 vía socket TCP (puente MQL4 ↔ Python en `bridge/`)

## Mapa de carpetas

| Ruta | Responsabilidad |
|---|---|
| `aurum.py` | Punto de entrada. Añade `src/` al path y orquesta el ciclo. |
| `src/config.py` | Constantes globales (host MT4, símbolo, magic number). |
| `src/scheduler.py` | Control de tiempo de ciclo, fin de semana, backoff de error. |
| `src/tui.py` | Interfaz textual (textual). API: `TUI.start/stop/log/update_*`. |
| `src/logger.py` | `AurumLogger`: escribe a `logs/aurum.log` y al TUI simultáneamente. |
| `src/agent/caller.py` | Llama a `claude` CLI en subproceso, parsea JSON de vuelta. |
| `src/bridge/mt4_client.py` | Cliente TCP para MT4. Lanza `MT4ConnectionError` si falla. |
| `src/bridge/AURUM_Bridge.mq4` | Expert Advisor en MT4 que sirve el socket. |
| `src/data/processor.py` | Construye el contexto de mercado y lo serializa para el prompt. |
| `src/risk/executor.py` | Valida la decisión del agente y ejecuta órdenes en MT4. |
| `src/strategy/system_prompt.md` | Prompt de sistema del agente. Editar para cambiar la estrategia. |
| `tests/` | Scripts de prueba manual. No requieren MT4 ni agente activo. |
| `logs/` | Logs en runtime. Ignorados por git. |

## Comandos habituales

```bash
python aurum.py          # arrancar el bot
python tests/tui_demo.py # previsualizar el TUI con datos simulados
```

## Convenciones

- El agente devuelve JSON con `decision` ∈ {BUY, SELL, WAIT, CLOSE}.
- `confidence < 0.60` → executor fuerza WAIT sin abrir posición.
- Un solo símbolo (XAUUSD). Sin multiposición simultánea por diseño.
- Logs estructurados en `logs/aurum.log` (rotación manual).
