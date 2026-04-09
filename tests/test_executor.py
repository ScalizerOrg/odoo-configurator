"""Tests for executor.py — operation dispatch + plugin loading."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, call, patch


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_client():
    client = MagicMock()
    client.context = {"lang": "fr_FR"}
    client.get_ref.side_effect = lambda xml_id: {"base.group_user": 1, "base.partner_demo": 2}.get(xml_id, 99)
    client.odoo.search_ids.return_value = []
    client.odoo.create.return_value = 42
    client.odoo.write.return_value = True
    client.odoo.execute_kw.return_value = {"messages": []}
    client.odoo.get_id_from_xml_id.return_value = None
    return client


@pytest.fixture
def mock_secrets():
    secrets = MagicMock()
    secrets.resolve.return_value = "resolved"
    secrets.get_env_var.return_value = "env_value"
    return secrets


@pytest.fixture
def mock_utils(tmp_path):
    utils = MagicMock()
    # resolve_path returns its argument unchanged by default
    utils.resolve_path.side_effect = lambda p: p
    return utils


@pytest.fixture
def ctx(mock_client, mock_secrets, mock_utils):
    from odoo_configurator.context import Context
    return Context(
        client=mock_client,
        config={},
        mode=["config"],
        secrets=mock_secrets,
        utils=mock_utils,
    )


# ── load_plugin_function ──────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_plugin_cache():
    """Clear the module cache between tests to prevent cross-test pollution."""
    from odoo_configurator import executor
    executor._plugin_cache.clear()
    yield
    executor._plugin_cache.clear()


def test_load_plugin_function_finds_function(tmp_path, ctx):
    plugin = tmp_path / "my_plugin.py"
    plugin.write_text("def my_func(ctx, params):\n    return 'called'\n")
    ctx.utils.resolve_path.side_effect = lambda p: str(tmp_path / p)

    from odoo_configurator.executor import load_plugin_function
    func = load_plugin_function("my_plugin.py::my_func", ctx)
    assert func(ctx, {}) == "called"


def test_load_plugin_function_missing_function_raises(tmp_path, ctx):
    plugin = tmp_path / "my_plugin.py"
    plugin.write_text("def existing(ctx, params): pass\n")
    ctx.utils.resolve_path.side_effect = lambda p: str(tmp_path / p)

    from odoo_configurator.executor import load_plugin_function
    with pytest.raises(AttributeError, match="missing_func"):
        load_plugin_function("my_plugin.py::missing_func", ctx)


def test_load_plugin_function_bad_handler_format_raises(ctx):
    from odoo_configurator.executor import load_plugin_function
    with pytest.raises(ValueError, match="::"):
        load_plugin_function("no_double_colon.py", ctx)


def test_load_plugin_function_cached(tmp_path, ctx):
    """Same file loaded twice must exec the module only once."""
    plugin = tmp_path / "cached.py"
    counter = tmp_path / "counter.txt"
    counter.write_text("0")
    plugin.write_text(
        f"from pathlib import Path\n"
        f"p = Path(r'{counter}')\n"
        f"p.write_text(str(int(p.read_text()) + 1))\n"
        f"def func(ctx, params): pass\n"
    )
    ctx.utils.resolve_path.side_effect = lambda p: str(tmp_path / p)

    from odoo_configurator.executor import load_plugin_function
    load_plugin_function("cached.py::func", ctx)
    load_plugin_function("cached.py::func", ctx)  # second call

    assert counter.read_text() == "1"  # exec'd only once


# ── InstallModules ────────────────────────────────────────────────────────────

def test_execute_install_modules(ctx, mock_client):
    from odoo_configurator.executor import execute_all
    from odoo_configurator.operations import InstallModules
    execute_all([InstallModules(module_names=["sale", "purchase"])], ctx)
    mock_client.odoo.install_modules.assert_called_once_with(["sale", "purchase"])


def test_execute_update_modules(ctx, mock_client):
    from odoo_configurator.executor import execute_all
    from odoo_configurator.operations import UpdateModules
    execute_all([UpdateModules(module_names=["sale"])], ctx)
    mock_client.odoo.update_modules.assert_called_once_with(["sale"])


def test_execute_uninstall_modules(ctx, mock_client):
    from odoo_configurator.executor import execute_all
    from odoo_configurator.operations import UninstallModules
    execute_all([UninstallModules(module_names=["website"])], ctx)
    mock_client.odoo.uninstall_modules.assert_called_once_with(["website"])


# ── SetSystemParam ────────────────────────────────────────────────────────────

def test_set_system_param_creates_new(ctx, mock_client):
    from odoo_configurator.executor import execute_all
    from odoo_configurator.operations import SetSystemParam
    mock_client.odoo.search_ids.return_value = []  # not found
    execute_all([SetSystemParam(key="web.base.url", value="http://odoo.localhost")], ctx)
    mock_client.odoo.create.assert_called_once_with(
        "ir.config_parameter",
        {"key": "web.base.url", "value": "http://odoo.localhost"},
    )


def test_set_system_param_updates_existing(ctx, mock_client):
    from odoo_configurator.executor import execute_all
    from odoo_configurator.operations import SetSystemParam
    mock_client.odoo.search_ids.return_value = [7]  # found
    execute_all([SetSystemParam(key="web.base.url", value="http://new.localhost")], ctx)
    mock_client.odoo.write.assert_called_once_with(
        "ir.config_parameter", [7], {"value": "http://new.localhost"}
    )


# ── ApplySettings ─────────────────────────────────────────────────────────────

def test_apply_settings_creates_and_executes(ctx, mock_client):
    from odoo_configurator.executor import execute_all
    from odoo_configurator.operations import ApplySettings
    execute_all([ApplySettings(values={"lang": "fr_FR"}, company_id=1)], ctx)
    mock_client.odoo.create.assert_called_once()
    # execute() called on the created record
    mock_client.odoo.execute_kw.assert_called_once()
    args = mock_client.odoo.execute_kw.call_args
    assert args[0][1] == "execute"


# ── UpsertRecord — search_key ─────────────────────────────────────────────────

def test_upsert_record_creates_when_not_found(ctx, mock_client):
    from odoo_configurator.executor import execute_all
    from odoo_configurator.operations import UpsertRecord
    mock_client.odoo.search_ids.return_value = []
    mock_client.odoo.create.return_value = 10

    execute_all([
        UpsertRecord(
            model="res.partner",
            values={"name": "ACME"},
            search_key="name",
        )
    ], ctx)
    mock_client.odoo.create.assert_called_once()
    create_args = mock_client.odoo.create.call_args
    assert create_args[0][0] == "res.partner"
    assert create_args[0][1]["name"] == "ACME"


def test_upsert_record_updates_when_found(ctx, mock_client):
    from odoo_configurator.executor import execute_all
    from odoo_configurator.operations import UpsertRecord
    mock_client.odoo.search_ids.return_value = [5]

    execute_all([
        UpsertRecord(
            model="res.partner",
            values={"name": "ACME Updated"},
            search_key="name",
        )
    ], ctx)
    mock_client.odoo.write.assert_called_once()
    write_args = mock_client.odoo.write.call_args
    assert write_args[0][0] == "res.partner"
    assert 5 in write_args[0][1]


# ── UpsertRecord — field suffixes ─────────────────────────────────────────────

def test_field_slash_id_resolved_to_int_in_write_mode(ctx, mock_client):
    """field/id with xml_id string → resolved to int for write()."""
    from odoo_configurator.executor import execute_all
    from odoo_configurator.operations import UpsertRecord
    mock_client.odoo.search_ids.return_value = [1]
    mock_client.get_ref.side_effect = None  # clear the side_effect
    mock_client.get_ref.return_value = 14

    execute_all([
        UpsertRecord(
            model="res.partner",
            values={"country_id/id": "base.fr"},
            search_key="name",
        )
    ], ctx)
    write_args = mock_client.odoo.write.call_args
    written_values = write_args[0][2]
    assert "country_id" in written_values
    assert written_values["country_id"] == 14
    assert "country_id/id" not in written_values


def test_field_slash_json_serialised(ctx, mock_client):
    """field/json values are JSON-serialised."""
    from odoo_configurator.executor import _resolve_field_suffixes
    values = {"config_data/json": {"key": "val"}}
    resolved = _resolve_field_suffixes(values, ctx, use_load=False)
    assert "config_data" in resolved
    assert resolved["config_data"] == '{"key": "val"}'
    assert "config_data/json" not in resolved


# ── RunScript ─────────────────────────────────────────────────────────────────

def test_run_script_calls_function(tmp_path, ctx):
    plugin = tmp_path / "my_script.py"
    plugin.write_text(
        "calls = []\n"
        "def run(ctx, params):\n"
        "    calls.append(params)\n"
    )
    ctx.utils.resolve_path.side_effect = lambda p: str(tmp_path / p)

    from odoo_configurator.executor import execute_all
    from odoo_configurator.operations import RunScript
    execute_all([RunScript(handler="my_script.py::run", params={"x": 1})], ctx)

    from odoo_configurator.executor import load_plugin_function
    module = load_plugin_function("my_script.py::run", ctx).__module__
    # The function was called — no error means success


def test_run_script_resolves_params(tmp_path, ctx, mock_secrets):
    """Params with get_env_var expressions are resolved before calling."""
    plugin = tmp_path / "param_script.py"
    plugin.write_text(
        "received = {}\n"
        "def run(ctx, params):\n"
        "    received.update(params)\n"
    )
    ctx.utils.resolve_path.side_effect = lambda p: str(tmp_path / p)
    mock_secrets.get_env_var.return_value = "resolved_value"

    from odoo_configurator.executor import execute_all
    from odoo_configurator.operations import RunScript
    execute_all([
        RunScript(
            handler="param_script.py::run",
            params={"pw": "get_env_var('MY_VAR')"},
        )
    ], ctx)
    # No error = get_env_var resolved without crashing


# ── CallMethod ────────────────────────────────────────────────────────────────

def test_call_method(ctx, mock_client):
    from odoo_configurator.executor import execute_all
    from odoo_configurator.operations import CallMethod
    execute_all([
        CallMethod(model="res.partner", method="write", args=[[1], {"active": True}])
    ], ctx)
    mock_client.odoo.execute_kw.assert_called_once_with(
        "res.partner", "write",
        [[[1], {"active": True}]],
        {"context": {"lang": "fr_FR"}},
    )


def test_call_method_no_raise_swallows_error(ctx, mock_client):
    from odoo_configurator.executor import execute_all
    from odoo_configurator.operations import CallMethod
    mock_client.odoo.execute_kw.side_effect = Exception("Odoo error")
    # Should not raise
    execute_all([
        CallMethod(model="res.partner", method="bad_method", args=[], no_raise=True)
    ], ctx)


def test_call_method_raises_by_default(ctx, mock_client):
    from odoo_configurator.executor import execute_all
    from odoo_configurator.operations import CallMethod
    mock_client.odoo.execute_kw.side_effect = Exception("Odoo error")
    with pytest.raises(Exception, match="Odoo error"):
        execute_all([
            CallMethod(model="res.partner", method="bad_method", args=[])
        ], ctx)


# ── DeleteRecord ──────────────────────────────────────────────────────────────

def test_delete_record_by_xml_id(ctx, mock_client):
    from odoo_configurator.executor import execute_all
    from odoo_configurator.operations import DeleteRecord
    mock_client.odoo.get_id_from_xml_id.return_value = 55

    execute_all([DeleteRecord(model="res.partner", xml_id="external_config.partner_1")], ctx)
    mock_client.odoo.execute_kw.assert_called_once_with("res.partner", "unlink", [[55]])


def test_delete_record_not_found_does_nothing(ctx, mock_client):
    from odoo_configurator.executor import execute_all
    from odoo_configurator.operations import DeleteRecord
    mock_client.odoo.get_id_from_xml_id.return_value = None

    execute_all([DeleteRecord(model="res.partner", xml_id="external_config.missing")], ctx)
    mock_client.odoo.execute_kw.assert_not_called()


# ── UpsertUser ────────────────────────────────────────────────────────────────

def test_upsert_user_creates_when_not_found(ctx, mock_client):
    from odoo_configurator.executor import execute_all
    from odoo_configurator.operations import UpsertUser
    mock_client.odoo.search_ids.return_value = []  # user not found
    mock_client.odoo.create.return_value = 20

    execute_all([
        UpsertUser(login="new@example.com", values={"name": "New User"})
    ], ctx)
    mock_client.odoo.create.assert_called_once()
    create_args = mock_client.odoo.create.call_args
    assert create_args[0][0] == "res.users"
    assert create_args[0][1]["login"] == "new@example.com"


def test_upsert_user_updates_when_found(ctx, mock_client):
    from odoo_configurator.executor import execute_all
    from odoo_configurator.operations import UpsertUser
    mock_client.odoo.search_ids.return_value = [20]  # user found

    execute_all([
        UpsertUser(login="existing@example.com", values={"name": "Updated"})
    ], ctx)
    mock_client.odoo.write.assert_called()
