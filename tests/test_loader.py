"""Tests for loader.py — YAML loading, merging, includes, sequence, and legacy key handling."""

import logging
import pytest
from pathlib import Path

from odoo_configurator.loader import ConfigLoader, _deep_merge


# ── _deep_merge unit tests ────────────────────────────────────────────────────

def test_deep_merge_simple():
    result = _deep_merge({"a": 1, "b": 2}, {"b": 3, "c": 4})
    assert result == {"a": 1, "b": 3, "c": 4}


def test_deep_merge_nested():
    base = {"section": {"a": 1, "b": 2}}
    override = {"section": {"b": 99, "c": 3}}
    result = _deep_merge(base, override)
    assert result == {"section": {"a": 1, "b": 99, "c": 3}}


def test_deep_merge_list_replaced_not_extended():
    """Lists are replaced wholesale — not concatenated."""
    result = _deep_merge({"modules": ["sale"]}, {"modules": ["purchase"]})
    assert result["modules"] == ["purchase"]


def test_deep_merge_does_not_mutate_inputs():
    base = {"a": {"x": 1}}
    override = {"a": {"y": 2}}
    _deep_merge(base, override)
    assert base == {"a": {"x": 1}}


# ── load_for_planning — single file (no sequence) ────────────────────────────

def test_load_single_file(tmp_path):
    f = tmp_path / "config.yml"
    f.write_text("name: test\nversion: 17.0\n")
    loader = ConfigLoader()
    result = loader.load_for_planning([f])
    assert len(result) == 1
    assert result[0]["name"] == "test"
    assert result[0]["version"] == 17.0


def test_load_multiple_files_merged(tmp_path):
    """Multiple CLI files are deep-merged (later files win)."""
    base = tmp_path / "base.yml"
    base.write_text("name: base\nmodule: sale\n")
    override = tmp_path / "prod.yml"
    override.write_text("name: prod\n")
    loader = ConfigLoader()
    result = loader.load_for_planning([base, override])
    assert len(result) == 1
    assert result[0]["name"] == "prod"
    assert result[0]["module"] == "sale"


def test_includes_resolved_relative(tmp_path):
    included = tmp_path / "base.yml"
    included.write_text("Base:\n  modules:\n    - sale\n")
    main = tmp_path / "main.yml"
    main.write_text("includes:\n  - base.yml\nname: main\n")
    loader = ConfigLoader()
    result = loader.load_for_planning([main])
    assert result[0]["name"] == "main"
    assert result[0]["Base"]["modules"] == ["sale"]


def test_includes_merged_deep(tmp_path):
    a = tmp_path / "a.yml"
    a.write_text("section:\n  x: 1\n  y: 2\n")
    b = tmp_path / "b.yml"
    b.write_text("includes:\n  - a.yml\nsection:\n  y: 99\n  z: 3\n")
    loader = ConfigLoader()
    result = loader.load_for_planning([b])
    assert result[0]["section"] == {"x": 1, "y": 99, "z": 3}


def test_includes_current_file_overrides_included(tmp_path):
    """Values in the file declaring `includes` override the included files."""
    included = tmp_path / "included.yml"
    included.write_text("name: from_included\n")
    main = tmp_path / "main.yml"
    main.write_text("includes:\n  - included.yml\nname: from_main\n")
    loader = ConfigLoader()
    result = loader.load_for_planning([main])
    assert result[0]["name"] == "from_main"


def test_circular_include_skipped(tmp_path, caplog):
    a = tmp_path / "a.yml"
    a.write_text("includes:\n  - b.yml\nname: a\n")
    b = tmp_path / "b.yml"
    b.write_text("includes:\n  - a.yml\nname: b\n")
    loader = ConfigLoader()
    with caplog.at_level(logging.WARNING):
        result = loader.load_for_planning([a])
    assert "Circular include" in caplog.text
    assert result[0]["name"] in ("a", "b")  # doesn't crash


def test_missing_include_raises(tmp_path):
    main = tmp_path / "main.yml"
    main.write_text("includes:\n  - nonexistent.yml\n")
    loader = ConfigLoader()
    with pytest.raises(FileNotFoundError, match="nonexistent.yml"):
        loader.load_for_planning([main])


# ── load_for_planning — sequence: expansion ───────────────────────────────────

def test_sequence_no_sequence_key_returns_single(tmp_path):
    f = tmp_path / "single.yml"
    f.write_text("name: single\n")
    loader = ConfigLoader()
    result = loader.load_for_planning([f])
    assert len(result) == 1
    assert result[0]["name"] == "single"


def test_sequence_ordered(tmp_path):
    s1 = tmp_path / "step1.yml"
    s1.write_text("name: step1\n")
    s2 = tmp_path / "step2.yml"
    s2.write_text("name: step2\n")
    main = tmp_path / "main.yml"
    main.write_text("sequence:\n  - step1.yml\n  - step2.yml\n")
    loader = ConfigLoader()
    result = loader.load_for_planning([main])
    assert [r["name"] for r in result] == ["step1", "step2"]


def test_sequence_recursive(tmp_path):
    """sequence: files can themselves contain sequence:."""
    s1 = tmp_path / "s1.yml"
    s1.write_text("name: s1\n")
    s2 = tmp_path / "s2.yml"
    s2.write_text("name: s2\n")
    group = tmp_path / "group.yml"
    group.write_text("sequence:\n  - s1.yml\n  - s2.yml\n")
    s3 = tmp_path / "s3.yml"
    s3.write_text("name: s3\n")
    root = tmp_path / "root.yml"
    root.write_text("sequence:\n  - group.yml\n  - s3.yml\n")
    loader = ConfigLoader()
    result = loader.load_for_planning([root])
    assert [r["name"] for r in result] == ["s1", "s2", "s3"]


def test_sequence_step_can_use_includes(tmp_path):
    """A file referenced by sequence: can itself use includes:."""
    common = tmp_path / "common.yml"
    common.write_text("Base:\n  config:\n    setting: true\n")
    step = tmp_path / "step.yml"
    step.write_text("includes:\n  - common.yml\nname: step\n")
    main = tmp_path / "main.yml"
    main.write_text("sequence:\n  - step.yml\n")
    loader = ConfigLoader()
    result = loader.load_for_planning([main])
    assert len(result) == 1
    assert result[0]["name"] == "step"
    assert result[0]["Base"]["config"]["setting"] is True


def test_sequence_circular_skipped(tmp_path, caplog):
    a = tmp_path / "a.yml"
    a.write_text("sequence:\n  - b.yml\n")
    b = tmp_path / "b.yml"
    b.write_text("sequence:\n  - a.yml\n")
    loader = ConfigLoader()
    with caplog.at_level(logging.WARNING):
        result = loader.load_for_planning([a])
    assert "Circular sequence" in caplog.text


def test_sequence_step_cannot_include_sequence_parent(tmp_path, caplog):
    """A sequence step that tries to include its sequence parent is skipped (circular)."""
    parent = tmp_path / "main.yml"
    parent.write_text("sequence:\n  - step.yml\n")
    step = tmp_path / "step.yml"
    step.write_text("includes:\n  - main.yml\nname: step\n")
    loader = ConfigLoader()
    with caplog.at_level(logging.WARNING):
        result = loader.load_for_planning([parent])
    assert "Circular include" in caplog.text
    assert result[0]["name"] == "step"


def test_sequence_entry_point_auth_preserved(tmp_path):
    """auth: in an entry point file is not lost when the file also has sequence:."""
    step = tmp_path / "step.yml"
    step.write_text("name: step\n")
    main = tmp_path / "main.yml"
    main.write_text("auth:\n  url: http://localhost\n  db: test\nsequence:\n  - step.yml\n")
    loader = ConfigLoader()
    result = loader.load_for_planning([main])
    assert result[0].get("auth", {}).get("url") == "http://localhost"
    assert result[1]["name"] == "step"


# ── Legacy key handling ───────────────────────────────────────────────────────

def test_legacy_inherits_remapped(tmp_path, caplog):
    """'inherits' is remapped to 'includes' with a deprecation warning."""
    included = tmp_path / "base.yml"
    included.write_text("name: base\n")
    main = tmp_path / "main.yml"
    main.write_text("inherits:\n  - base.yml\nname: main\n")
    loader = ConfigLoader()
    with caplog.at_level(logging.WARNING):
        result = loader.load_for_planning([main])
    assert "inherits" in caplog.text
    assert "Deprecated" in caplog.text
    assert result[0]["name"] == "main"


def test_legacy_script_files_remapped(tmp_path, caplog):
    """'script_files' is remapped to 'sequence' with a deprecation warning."""
    s = tmp_path / "step.yml"
    s.write_text("name: step\n")
    main = tmp_path / "main.yml"
    main.write_text("script_files:\n  - step.yml\nname: main\n")
    loader = ConfigLoader()
    with caplog.at_level(logging.WARNING):
        result = loader.load_for_planning([main])
    assert "script_files" in caplog.text
    assert "Deprecated" in caplog.text


# ── configurator_version check ────────────────────────────────────────────────

def test_version_check_passes():
    loader = ConfigLoader()
    loader.check_configurator_version({"configurator_version": "3.0.0"}, "4.0.0")  # no exception


def test_version_check_no_key():
    loader = ConfigLoader()
    loader.check_configurator_version({}, "4.0.0")  # no exception


def test_version_check_fails():
    loader = ConfigLoader()
    with pytest.raises(SystemExit):
        loader.check_configurator_version({"configurator_version": "99.0.0"}, "4.0.0")
