"""Tests for utils.py — path resolution."""

import pytest
from pathlib import Path
from odoo_configurator.utils import Utils


@pytest.fixture
def base(tmp_path):
    """Return a Utils instance anchored to tmp_path."""
    return Utils(base_path=tmp_path)


# ── resolve_path ──────────────────────────────────────────────────────────────

def test_resolve_absolute_path(base, tmp_path):
    f = tmp_path / "absolute.csv"
    f.write_text("data")
    result = base.resolve_path(str(f))
    assert result == str(f.resolve())


def test_resolve_relative_to_base(base, tmp_path):
    f = tmp_path / "partners.csv"
    f.write_text("data")
    result = base.resolve_path("partners.csv")
    assert result == str(f.resolve())


def test_resolve_relative_to_base_datas(base, tmp_path):
    datas_dir = tmp_path / "datas"
    datas_dir.mkdir()
    f = datas_dir / "products.csv"
    f.write_text("data")
    result = base.resolve_path("products.csv")
    assert result == str(f.resolve())


def test_resolve_direct_match_preferred_over_datas(base, tmp_path):
    """If the file exists in base_path, that takes priority over datas/."""
    datas_dir = tmp_path / "datas"
    datas_dir.mkdir()
    f_base = tmp_path / "file.csv"
    f_datas = datas_dir / "file.csv"
    f_base.write_text("base")
    f_datas.write_text("datas")
    result = base.resolve_path("file.csv")
    assert result == str(f_base.resolve())


def test_resolve_not_found_raises(base):
    with pytest.raises(FileNotFoundError, match="missing.csv"):
        base.resolve_path("missing.csv")


def test_resolve_empty_string_returns_empty(base):
    assert base.resolve_path("") == ""


# ── resolve_dir ───────────────────────────────────────────────────────────────

def test_resolve_dir_relative(base, tmp_path):
    d = tmp_path / "exports"
    d.mkdir()
    result = base.resolve_dir("exports")
    assert result == str(d.resolve())


def test_resolve_dir_in_datas(base, tmp_path):
    datas = tmp_path / "datas"
    datas.mkdir()
    sub = datas / "exports"
    sub.mkdir()
    result = base.resolve_dir("exports")
    assert result == str(sub.resolve())


def test_resolve_dir_not_found_raises(base):
    with pytest.raises(NotADirectoryError, match="missing_dir"):
        base.resolve_dir("missing_dir")


# ── Default base_path (cwd) ───────────────────────────────────────────────────

def test_default_base_path_is_cwd():
    utils = Utils()
    assert utils.base_path == Path.cwd()
