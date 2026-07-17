"""campaign_manager.py — Save/load/delete campaign presets as JSON."""

import json
from pathlib import Path

PRESETS_DIR = Path("campaigns")
PRESETS_FILE = PRESETS_DIR / "presets.json"


def _ensure_dir() -> None:
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)


def _read() -> dict:
    _ensure_dir()
    if not PRESETS_FILE.exists():
        return {}
    try:
        with open(PRESETS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _write(data: dict) -> None:
    _ensure_dir()
    with open(PRESETS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_presets() -> dict:
    """Return the full presets dict {name: {fields...}}."""
    return _read()


def save_preset(name: str, preset_data: dict) -> None:
    """Save or overwrite a named preset."""
    data = _read()
    data[name.strip()] = preset_data
    _write(data)


def delete_preset(name: str) -> None:
    """Remove a preset by name (no-op if missing)."""
    data = _read()
    data.pop(name, None)
    _write(data)


def get_preset_names() -> list[str]:
    """Return sorted list of saved preset names."""
    return sorted(_read().keys())
