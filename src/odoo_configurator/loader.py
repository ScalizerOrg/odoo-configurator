# Copyright 2025 Scalizer (<https://www.scalizer.fr>)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

"""
Config loader — reads, merges, and resolves YAML configuration files.

Uses plain PyYAML; all dicts are standard Python dicts. Supports:
  - includes:  merge multiple files (deep merge, later files win)
  - sequence:  execute files sequentially without merging (DI / migration mode)
  - configurator_version: minimum version enforcement
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
from packaging.version import Version

logger = logging.getLogger(__name__)

# ── Legacy key aliases (deprecated in v4, removed in v5) ─────────────────────
# LEGACY: these keys are mapped to their new equivalents with a deprecation warning.
_LEGACY_KEYS = {
    "inherits": "includes",
    "script_files": "sequence",
}


def _warn_legacy(old_key: str, new_key: str, source: str) -> None:
    logger.warning(
        "Deprecated key '%s' in '%s' — use '%s' instead. "
        "Legacy keys will be removed in v5.",
        old_key, source, new_key,
    )


def _load_yaml(path: Path) -> dict:
    """Load a single YAML file as a plain dict."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a YAML mapping at the top level, got {type(data)}")
    return data


def _normalise_keys(data: dict, source: str) -> dict:
    """Rename legacy keys and emit deprecation warnings."""
    for old, new in _LEGACY_KEYS.items():
        if old in data:
            _warn_legacy(old, new, source)
            if new not in data:
                data[new] = data.pop(old)
            else:
                # Both old and new present — new takes precedence, old is discarded.
                del data[old]
    return data


def _deep_merge(base: dict, override: dict) -> dict:
    """
    Recursively merge two dicts. override wins on scalar conflicts.
    Lists are replaced entirely (not extended) — same behaviour as HiYaPyCo METHOD_MERGE
    for the keys we care about (modules, updates, etc.).
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _resolve_path(ref: str, relative_to: Path, search_dirs: list[Path]) -> Path:
    """
    Resolve a file reference to an absolute Path.
    Search order:
      1. Absolute path as-is
      2. Relative to the file that declared the reference
      3. Each directory in search_dirs (template dirs)
    """
    p = Path(ref)
    if p.is_absolute() and p.is_file():
        return p
    candidate = relative_to / p
    if candidate.is_file():
        return candidate.resolve()
    for d in search_dirs:
        candidate = d / p
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        f"Config file not found: '{ref}' (looked relative to '{relative_to}' "
        f"and in {[str(d) for d in search_dirs]})"
    )


class ConfigLoader:
    """
    Loads and resolves a configuration from one or more YAML files.

    Usage:
        loader = ConfigLoader(search_dirs=[Path("templates")])
        configs = loader.load_for_planning([Path("main.yml")])
        # Returns an ordered list of config dicts — one per sequence step.
    """

    def __init__(self, search_dirs: list[Path] | None = None):
        self.search_dirs: list[Path] = search_dirs or []

    # ── Public API ────────────────────────────────────────────────────────────

    def load_for_planning(self, paths: list[Path]) -> list[dict]:
        """
        Load config file(s) and return an ordered list of config dicts to plan.

        - Single path with sequence:: expands to N dicts (one per sequence step).
        - Multiple CLI paths: deep-merged into one dict (environment overlay pattern).
        - includes: inside any file: merged at load time (existing behaviour, unchanged).
        """
        if len(paths) > 1:
            merged: dict = {}
            for path in paths:
                data = self._load_with_includes(path.resolve())
                merged = _deep_merge(merged, data)
            return [merged]
        return self._expand_sequence(paths[0].resolve())

    def _expand_sequence(
        self,
        path: Path,
        seen: frozenset[Path] | None = None,
    ) -> list[dict]:
        """
        Load a file (resolving includes:), then expand sequence: into an ordered list.
        Returns [config] for files without sequence:, or [config_A, config_B, ...]
        for files that declare a sequence:.
        """
        seen = (seen or frozenset()) | {path}
        data = self._load_with_includes(path, _seen=seen)

        sequence_refs = data.pop("sequence", [])
        if not sequence_refs:
            return [data]

        result: list[dict] = [data] if data else []
        for ref in sequence_refs:
            child_path = _resolve_path(ref, path.parent, self.search_dirs)
            if child_path in seen:
                logger.warning("Circular sequence detected: '%s' — skipping.", child_path)
                continue
            result.extend(self._expand_sequence(child_path, seen))
        return result

    def check_configurator_version(self, config: dict, current_version: str) -> None:
        """
        Raise SystemExit if the config requires a higher configurator version
        than the one currently running.
        """
        required = config.get("configurator_version")
        if not required:
            return
        required = str(required)
        if Version(required) > Version(current_version):
            logger.error(
                "This configuration requires odoo-configurator >= %s "
                "(running %s). Please upgrade.",
                required, current_version,
            )
            raise SystemExit(1)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _load_with_includes(self, path: Path, _seen: frozenset[Path] | None = None) -> dict:
        """Load a YAML file and recursively merge its `includes:` files."""
        seen = (_seen or frozenset()) | {path}
        data = _load_yaml(path)
        data = _normalise_keys(data, str(path))

        include_refs = data.pop("includes", [])
        if not include_refs:
            return data

        # Merge included files first, then overlay the current file on top.
        base: dict = {}
        for ref in include_refs:
            child_path = _resolve_path(ref, path.parent, self.search_dirs)
            if child_path in seen:
                logger.warning("Circular include detected: '%s' — skipping.", child_path)
                continue
            child_data = self._load_with_includes(child_path, seen)
            base = _deep_merge(base, child_data)

        return _deep_merge(base, data)
