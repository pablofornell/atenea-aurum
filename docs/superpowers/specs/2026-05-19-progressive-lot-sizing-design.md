# Diseño: Lotaje Progresivo Basado en Balance

**Fecha:** 2026-05-19  
**Estado:** Aprobado

## Resumen

Reemplazar el sistema de lotaje basado en riesgo porcentual (`MAX_RISK_PCT`) por un sistema progresivo clásico donde cada $100 de balance corresponde a 0.01 lot. `FIXED_LOTS` se mantiene como override manual con prioridad total.

## Fórmula

```
lots = floor(balance / BALANCE_LOT_STEP) × 0.01
lots = clamp(lots, broker_min_lot, broker_max_lot)
```

Con `BALANCE_LOT_STEP = 100` (configurable):

| Balance | lots calculado | lots final |
|---|---|---|
| $80 | 0.00 | broker min (≥0.01) |
| $100 | 0.01 | 0.01 |
| $150 | 0.01 | 0.01 |
| $200 | 0.02 | 0.02 |
| $999 | 0.09 | 0.09 |
| $1000 | 0.10 | 0.10 |
| $5000 | 0.50 | 0.50 |

- **Redondeo:** floor (truncar). Conservador: nunca se excede el tramo.
- **Suelo:** mínimo del broker (vía `mt4.get_symbol_info`). Si el cálculo da 0, se usa `min_lot`.
- **Techo:** máximo del broker. El `_snap_lots` existente ya aplica ambos límites.

## Cambios requeridos

### `src/config.py`

- **Añadir:** `BALANCE_LOT_STEP = 100` — tramo en dólares por 0.01 lot.
- **Eliminar:** `MAX_RISK_PCT` — ya no se usa en ninguna ruta de ejecución.

### `src/risk/executor.py`

Sustituir el bloque de lot sizing (líneas 187-192) por:

```python
import math

using_fixed_lots = getattr(cfg, "FIXED_LOTS", 0.0) > 0
if using_fixed_lots:
    lots = cfg.FIXED_LOTS
else:
    step = getattr(cfg, "BALANCE_LOT_STEP", 100)
    lots = math.floor(balance / step) * 0.01
```

El clamp al rango del broker lo aplica `_snap_lots` dentro de `_attempt_order`, que ya existe y no requiere cambios.

## Lo que NO cambia

- `FIXED_LOTS`: si `> 0`, sigue teniendo prioridad total sobre el progresivo.
- `_snap_lots`, `_attempt_order`, `_DD_GUARD`: sin cambios.
- Validaciones de SL, TP, R:R, drawdown guard: sin cambios.
- Ambos modos (demo/prod): comparten la misma lógica de sizing.

## Decisiones de diseño

| Decisión | Elección | Razón |
|---|---|---|
| Integración con modos existentes | Reemplaza risk-based, mantiene FIXED_LOTS | Coherente con estilo actual; FIXED_LOTS cubre el caso de override manual |
| Balance < $100 | Usa mínimo del broker | No bloquea el trading; deja operar con el lote mínimo |
| Redondeo | Floor / truncar | Conservador; nunca se arriesga más de lo que indica el tramo |
| Parámetro en config | `BALANCE_LOT_STEP` | Igual que `FIXED_LOTS`; configurable sin tocar la lógica |
