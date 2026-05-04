"""
Load and save structural state JSON with backup.
"""

import json
import os
import shutil
from pathlib import Path

from state.schema import default_state, SCHEMA_VERSION


def load_state(path: str) -> dict:
    """Load state from JSON file. Returns empty default state if file missing or corrupt."""
    p = Path(path)
    if not p.exists():
        return default_state()

    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return default_state()

    # Migrate schema if needed (forward-compatible: just return defaults for unknown versions)
    if data.get("schema_version") != SCHEMA_VERSION:
        return default_state()

    # Fill any missing keys from defaults (graceful forward-compat)
    defaults = default_state()
    _deep_merge_defaults(data, defaults)
    return data


def save_state(state: dict, path: str) -> None:
    """Save state to JSON file, keeping a backup of the previous version."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    backup = p.with_name("structural_state.previous.json")
    if p.exists():
        shutil.copy2(p, backup)

    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    tmp.replace(p)


def _deep_merge_defaults(data: dict, defaults: dict) -> None:
    """Fill missing keys in data with values from defaults (in-place, non-recursive for lists)."""
    for key, default_val in defaults.items():
        if key not in data:
            data[key] = default_val
        elif isinstance(default_val, dict) and isinstance(data.get(key), dict):
            _deep_merge_defaults(data[key], default_val)
