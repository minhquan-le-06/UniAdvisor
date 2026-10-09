"""Load versioned configuration: regulation rules per admission year and data-build settings."""

from __future__ import annotations

from functools import cache
from typing import Any

import yaml

from uniadvisor.paths import CONFIG_DIR, RULES_DIR


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_yaml(path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@cache
def load_rules(admission_year: int) -> dict[str, Any]:
    """Regulation facts for one admission year, following `inherits:` chains.

    A year file may override any key of the year it inherits from; nested mappings are merged.
    """
    path = RULES_DIR / f"{admission_year}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No rules for admission year {admission_year} ({path})")
    own = _read_yaml(path)
    parent_year = own.pop("inherits", None)
    if parent_year is None:
        return own
    if int(parent_year) >= admission_year:
        raise ValueError(f"Rules {admission_year} must inherit from an earlier year, not {parent_year}")
    return _deep_merge(load_rules(int(parent_year)), own)


@cache
def load_data_config() -> dict[str, Any]:
    return _read_yaml(CONFIG_DIR / "data.yaml")


@cache
def load_list_config() -> dict[str, Any]:
    return _read_yaml(CONFIG_DIR / "list.yaml")


@cache
def load_provinces() -> dict[str, str]:
    """Province name or alias -> home city ('HN' | 'HCM')."""
    out: dict[str, str] = {}
    for city, entries in _read_yaml(CONFIG_DIR / "provinces.yaml").items():
        for entry in entries:
            for name in [entry["name"], *entry.get("aliases", [])]:
                out[name] = city
    return out


def province_names() -> list[str]:
    """The provinces a student chooses from (no aliases), in file order."""
    data = _read_yaml(CONFIG_DIR / "provinces.yaml")
    return [entry["name"] for entries in data.values() for entry in entries]
