# Sistema de Logging y Feedback Loop de Aurum

## Visión general

Aurum tiene dos capas de logging:

1. **Log operacional** (`logs/aurum.log`) — salida estándar de Python logging para monitorización en tiempo real.
2. **Log estructurado de feedback** (`logs/aurum_events.jsonl`) — eventos JSON línea a línea para análisis post-sesión y mejora continua del sistema.

El objetivo del segundo es crear un **ciclo de retroalimentación**: cada sesión de trading genera un informe legible por humanos y por agentes de IA, que permite identificar bugs, comportamientos subóptimos y oportunidades de mejora de forma sistemática.

---

## Ficheros generados

| Fichero | Cuándo | Contenido |
|---------|--------|-----------|
| `logs/aurum.log` | Siempre, en tiempo real | Log operacional (INFO/WARNING/ERROR) |
| `logs/aurum_events.jsonl` | Siempre, append por sesión | Eventos estructurados JSON, una línea por evento |
| `logs/sessions/<ts>_<runid>.md` | Al terminar cada sesión | Informe markdown completo de la sesión |
| `logs/sessions/<runid>_review_prompt.txt` | Con `--prompt` | Prompt listo para pasar a Claude Code |

---

## Eventos registrados

Cada línea de `aurum_events.jsonl` tiene la estructura:

```json
{
  "ts": "2026-04-23T03:31:01.483Z",
  "run_id": "4f2a8c1d-...",
  "session_id": "4620821f-...",
  "turn": 1,
  "event": "claude_decision",
  "data": { ... }
}
```

### Tipos de evento

| Evento | Nivel | Captura |
|--------|-------|---------|
| `run_start` | run | Intervalo de ciclo, path del fichero de eventos |
| `run_end` | run | Duración total, ciclos, errores, balance inicial/final, P&L realizado |
| `cycle_start` | ciclo | Inicio de un nuevo ciclo |
| `cycle_end` | ciclo | Duración del ciclo, última acción ejecutada |
| `market_context` | turno | Precio bid/ask, cuenta, posiciones abiertas, flag `connection_ok` |
| `screenshot` | turno | Path de la captura de pantalla |
| `claude_decision` | turno | Tipo de acción, **razonamiento completo**, parámetros (SL/TP/lots), tiempo de respuesta Claude |
| `action_result` | turno | OK/error con detalle: ticket, SL, TP, causa del fallo |
| `error` | turno | Tipo clasificado + detalle + contexto |
| `reconnect` | run/ciclo | Éxito/fallo, número de intentos |
| `connection_lost` | turno | Detección de pérdida de conexión MT4 |

### Tipos de error clasificados

| Tipo | Causa |
|------|-------|
| `timeout` | Claude CLI no respondió en 120s |
| `connection` | Socket MT4 caído (WinError 10053/10054) |
| `modify_failed` | MT4 rechazó MODIFY (stop level del broker, stops inválidos) |
| `order_failed` | MT4 rechazó BUY/SELL/CLOSE |
| `duplicate_position` | Orden bloqueada porque ya hay una posición abierta |
| `screenshot` | Error capturando pantalla de MT4 |
| `parse_error` | Claude no devolvió JSON válido |
| `cycle_exception` | Excepción no capturada en el ciclo |

---

## Informe de sesión (markdown)

Al terminar la sesión (Ctrl+C), `aurum.py` genera automáticamente el informe y muestra los comandos para revisarlo:

```
[INFO] Generating session report...
[INFO] Report saved: logs/sessions/20260423_033101_4f2a8c1d.md
[INFO] Review with: python src/tools/review_session.py 4f2a8c1d
[INFO] Full prompt:  python src/tools/review_session.py 4f2a8c1d --prompt
```

### Estructura del informe

```markdown
# AURUM Session Report

- Run ID, período, duración, P&L realizado, balance

## Resumen estadístico
- Ciclos, acciones (DONE×18, MODIFY×7, SELL×1...), errores, reconexiones

## Detalle de ciclos
### 03:31:01 — ciclo 4620821f
Precio: bid=4732.22 ask=4732.44
Cuenta: balance=4515.38 equity=4515.38
Posiciones: ninguna

Decisión Claude: `SELL` (17.1s)
Parámetros: lots=0.1 | sl=4772.2 | tp=4664.66
> "Identifico resistencia en 4772 y tendencia bajista..."

Resultado: ✓ ticket=73553702

## Análisis de errores
### `modify_failed` (3 ocurrencias)
- ...

## Anomalías detectadas
- ...

## Sugerencias de mejora
> Sección para rellenar por el revisor (humano o agente).

### Comportamiento del agente
- [ ]
### Gestión de riesgo
- [ ]
### Infraestructura / conexión
- [ ]
### Calidad del prompt / razonamiento de Claude
- [ ]

## Referencias de código para el revisor
| Fichero | Relevancia |
...
```

---

## Herramienta de revisión: `review_session.py`

```bash
# Listar todas las sesiones grabadas
python src/tools/review_session.py

# Ver informe de la última sesión
python src/tools/review_session.py latest

# Ver informe de una sesión específica (prefijo del run_id)
python src/tools/review_session.py 4f2a8c1d

# Guardar el informe en logs/sessions/
python src/tools/review_session.py latest --save

# Generar prompt completo (informe + código fuente) para revisor IA
python src/tools/review_session.py latest --prompt
```

La opción `--prompt` genera `logs/sessions/<runid>_review_prompt.txt` con:
- El informe de sesión completo
- El código fuente de los ficheros clave (truncado a 6000 chars cada uno)
- Instrucciones para Claude sobre cómo analizar y proponer mejoras concretas

---

## Ciclo de retroalimentación completo

```
1. Ejecutar Aurum
   python aurum.py

2. Al parar (Ctrl+C), el informe se genera automáticamente
   logs/sessions/20260423_033101_4f2a8c1d.md

3. Revisar manualmente o con IA
   python src/tools/review_session.py latest --prompt --save
   # genera: logs/sessions/4f2a8c1d_review_prompt.txt

4. Pasar el prompt a Claude Code
   cat logs/sessions/4f2a8c1d_review_prompt.txt | claude --dangerously-skip-permissions

5. Claude propone cambios con fichero:línea específicos

6. Aplicar, hacer commit, volver al paso 1
```

---

## Módulos del sistema de logging

| Módulo | Descripción |
|--------|-------------|
| `src/agent/feedback_logger.py` | `FeedbackLogger` — escribe eventos JSONL. Se inicializa en `aurum.py` con un `run_id` único y se pasa al agente. |
| `src/agent/session_reporter.py` | `SessionReporter` — lee el JSONL y genera el informe markdown. Funciones: `generate_report(run_id)`, `list_runs()`. |
| `src/tools/review_session.py` | CLI de revisión. Punto de entrada para el operador. |

---

## Notas de diseño

- **`aurum_events.jsonl` es append-only**: cada ejecución añade al mismo fichero, con `run_id` para separar sesiones. No se sobreescribe entre ejecuciones.
- **El informe es idempotente**: se puede regenerar en cualquier momento con `generate_report(run_id)` sin necesidad de re-ejecutar el sistema.
- **Cero overhead en producción**: si `FeedbackLogger` no se pasa al agente (o falla al escribir), el sistema sigue funcionando normalmente.
- **La sección "Sugerencias de mejora"** del informe está intencionalmente vacía: es el espacio de trabajo del revisor, no se rellena automáticamente.
