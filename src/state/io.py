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

    # Migrate schema if needed — preserve bot memory across version bumps
    if data.get("schema_version") != SCHEMA_VERSION:
        new_state = default_state()
        old_bm = data.get("bot_managed", {})
        if isinstance(old_bm, dict):
            # v2→v3: rename h4_bias→h1_bias, h1_bias→m15_bias
            original_h1_bias = old_bm.get("h1_bias")
            original_h1_bias_justification = old_bm.get("h1_bias_justification", "")
            if "h4_bias" in old_bm:
                old_bm["h1_bias"] = old_bm.pop("h4_bias")
                old_bm["h1_bias_since"] = old_bm.pop("h4_bias_since", None)
                old_bm["h1_bias_justification"] = old_bm.pop("h4_bias_justification", "")
            if original_h1_bias is not None and "m15_bias" not in old_bm:
                old_bm["m15_bias"] = original_h1_bias
                old_bm["m15_bias_justification"] = original_h1_bias_justification
            elif "m15_bias" not in old_bm and "h1_bias" in old_bm:
                old_bm["m15_bias"] = old_bm.pop("h1_bias", "unclear")
                old_bm["m15_bias_justification"] = old_bm.pop("h1_bias_justification", "")
            from state.schema import validate_bot_managed
            ok, _ = validate_bot_managed(old_bm)
            if ok:
                new_state["bot_managed"] = old_bm
        old_decisions = data.get("code_managed", {}).get("recent_decisions", [])
        if old_decisions:
            new_state["code_managed"]["recent_decisions"] = old_decisions[-5:]
        return new_state

    # Fill any missing keys from defaults (graceful forward-compat)
    defaults = default_state()
    _deep_merge_defaults(data, defaults)
    return data


def save_state(state: dict, path: str) -> None:
    """Save state to JSON file, keeping a backup of the previous version."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    backup = p.with_name(f"{p.stem}.previous{p.suffix}")
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
