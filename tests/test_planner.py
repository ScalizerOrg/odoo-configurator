"""Tests for planner.py — config dict → ordered list of Operations."""

import pytest
from odoo_configurator.planner import build_plan, _METADATA_KEYS
from odoo_configurator.operations import (
    ApplySettings,
    CallMethod,
    ImportCSV,
    InstallModules,
    InstallTranslation,
    RunScript,
    SendMattermostMessage,
    SendSlackMessage,
    SetFieldDefault,
    SetSystemParam,
    UninstallModules,
    UpdateModules,
    UpsertRecord,
    UpsertRole,
    UpsertUser,
)


# ── Module operations ─────────────────────────────────────────────────────────

def test_install_modules():
    config = {"Base": {"modules": ["sale", "purchase"]}}
    ops = build_plan(config)
    assert InstallModules(module_names=["sale", "purchase"]) in ops


def test_update_modules():
    config = {"Base": {"updates": ["sale"]}}
    ops = build_plan(config)
    assert UpdateModules(module_names=["sale"]) in ops


def test_uninstall_modules():
    config = {"Base": {"uninstall_modules": ["website"]}}
    ops = build_plan(config)
    assert UninstallModules(module_names=["website"]) in ops


def test_module_list_as_string():
    config = {"Base": {"modules": "sale"}}
    ops = build_plan(config)
    assert InstallModules(module_names=["sale"]) in ops


def test_module_list_with_dict_entries():
    """Module entries with extra keys like on_install_only are accepted."""
    config = {"Base": {"modules": [{"name": "sale"}, "purchase"]}}
    ops = build_plan(config)
    assert InstallModules(module_names=["sale", "purchase"]) in ops


# ── Translations ──────────────────────────────────────────────────────────────

def test_top_level_translations():
    config = {"translations": ["fr_FR", "nl_NL"]}
    ops = build_plan(config)
    assert InstallTranslation(lang_code="fr_FR") in ops
    assert InstallTranslation(lang_code="nl_NL") in ops


def test_section_level_translations():
    config = {"Base": {"translations": ["de_DE"]}}
    ops = build_plan(config)
    assert InstallTranslation(lang_code="de_DE") in ops


# ── System parameters ─────────────────────────────────────────────────────────

def test_system_parameter():
    config = {"Params": {"system_parameter": {"web.base.url": "http://odoo.localhost"}}}
    ops = build_plan(config)
    assert SetSystemParam(key="web.base.url", value="http://odoo.localhost") in ops


def test_system_parameter_value_converted_to_string():
    config = {"Params": {"system_parameter": {"max_cron_threads": 4}}}
    ops = build_plan(config)
    assert SetSystemParam(key="max_cron_threads", value="4") in ops


# ── Settings ──────────────────────────────────────────────────────────────────

def test_config_settings():
    config = {"Settings": {"config": {"lang": "fr_FR", "company_id": 1}}}
    ops = build_plan(config)
    settings_ops = [op for op in ops if isinstance(op, ApplySettings)]
    assert len(settings_ops) == 1
    assert settings_ops[0].company_id == 1
    assert settings_ops[0].values.get("lang") == "fr_FR"
    # company_id is extracted from values, not left inside
    assert "company_id" not in settings_ops[0].values


# ── Datas records ─────────────────────────────────────────────────────────────

def test_datas_upsert_record():
    config = {
        "Partners": {
            "datas": {
                "ACME": {
                    "model": "res.partner",
                    "name": "ACME Corp",
                    "force_id": "external_config.partner_acme",
                }
            }
        }
    }
    ops = build_plan(config)
    upserts = [op for op in ops if isinstance(op, UpsertRecord)]
    assert len(upserts) == 1
    assert upserts[0].model == "res.partner"
    assert upserts[0].force_id == "external_config.partner_acme"
    assert upserts[0].values.get("name") == "ACME Corp"


def test_datas_record_without_model_skipped():
    config = {"Partners": {"datas": {"bad_record": {"name": "No Model"}}}}
    ops = build_plan(config)
    assert not any(isinstance(op, UpsertRecord) for op in ops)


def test_datas_section_languages_inherited():
    config = {
        "Partners": {
            "languages": ["fr_FR"],
            "datas": {
                "ACME": {"model": "res.partner", "name": "ACME"}
            }
        }
    }
    ops = build_plan(config)
    upserts = [op for op in ops if isinstance(op, UpsertRecord)]
    assert upserts[0].languages == ["fr_FR"]


def test_datas_record_languages_override_section():
    config = {
        "Partners": {
            "languages": ["fr_FR"],
            "datas": {
                "ACME": {"model": "res.partner", "name": "ACME", "languages": ["en_US"]}
            }
        }
    }
    ops = build_plan(config)
    upserts = [op for op in ops if isinstance(op, UpsertRecord)]
    assert upserts[0].languages == ["en_US"]


# ── Field defaults ────────────────────────────────────────────────────────────

def test_defaults():
    config = {
        "Defaults": {
            "defaults": {
                "Partner Type": {
                    "model": "res.partner",
                    "field": "company_type",
                    "value": "company",
                }
            }
        }
    }
    ops = build_plan(config)
    defaults_ops = [op for op in ops if isinstance(op, SetFieldDefault)]
    assert len(defaults_ops) == 1
    assert defaults_ops[0].model == "res.partner"
    assert defaults_ops[0].field == "company_type"
    assert defaults_ops[0].value == "company"


# ── Roles ─────────────────────────────────────────────────────────────────────

def test_datas_roles():
    config = {
        "Roles": {
            "datas_roles": {
                "role_sales": {
                    "force_id": "external_config.role_sales",
                    "values": {
                        "name": "Sales",
                        "implied_ids": ["base.group_user"],
                    }
                }
            }
        }
    }
    ops = build_plan(config)
    role_ops = [op for op in ops if isinstance(op, UpsertRole)]
    assert len(role_ops) == 1
    assert role_ops[0].name == "Sales"
    assert role_ops[0].implied_ids == ["base.group_user"]
    assert role_ops[0].force_id == "external_config.role_sales"


# ── Users ─────────────────────────────────────────────────────────────────────

def test_users():
    config = {
        "Users": {
            "users": {
                "admin@example.com": {
                    "login": "admin@example.com",
                    "values": {"name": "Admin"},
                    "groups_id": ["base.group_user"],
                }
            }
        }
    }
    ops = build_plan(config)
    user_ops = [op for op in ops if isinstance(op, UpsertUser)]
    assert len(user_ops) == 1
    assert user_ops[0].login == "admin@example.com"
    assert user_ops[0].groups == ["base.group_user"]


# ── Method calls ──────────────────────────────────────────────────────────────

def test_call():
    config = {
        "Calls": {
            "call": {
                "Activate portal": {
                    "model": "res.partner",
                    "method": "write",
                    "args": [[1], {"active": True}],
                }
            }
        }
    }
    ops = build_plan(config)
    call_ops = [op for op in ops if isinstance(op, CallMethod)]
    assert len(call_ops) == 1
    assert call_ops[0].model == "res.partner"
    assert call_ops[0].method == "write"


# ── CSV imports ───────────────────────────────────────────────────────────────

def test_import_data():
    config = {
        "Imports": {
            "import_data": {
                "Partners": {
                    "model": "res.partner",
                    "file_path": "datas/partners.csv",
                    "batch_size": 100,
                }
            }
        }
    }
    ops = build_plan(config)
    import_ops = [op for op in ops if isinstance(op, ImportCSV)]
    assert len(import_ops) == 1
    assert import_ops[0].model == "res.partner"
    assert import_ops[0].file_path == "datas/partners.csv"
    assert import_ops[0].batch_size == 100


def test_import_data_legacy_specific_import(recwarn):
    """specific_import + specific_method is deprecated but converted to handler."""
    config = {
        "Imports": {
            "import_data": {
                "Partners": {
                    "model": "res.partner",
                    "file_path": "datas/partners.csv",
                    "specific_import": "scripts/helpers.py",
                    "specific_method": "do_import",
                }
            }
        }
    }
    ops = build_plan(config)
    import_ops = [op for op in ops if isinstance(op, ImportCSV)]
    assert import_ops[0].handler == "scripts/helpers.py::do_import"


# ── Python scripts ────────────────────────────────────────────────────────────

def test_script_new_style():
    config = {
        "Scripts": {
            "script": {
                "Import Products": {
                    "handler": "scripts/products.py::import_products",
                    "params": {"csv_file": "datas/products.csv"},
                }
            }
        }
    }
    ops = build_plan(config)
    script_ops = [op for op in ops if isinstance(op, RunScript)]
    assert len(script_ops) == 1
    assert script_ops[0].handler == "scripts/products.py::import_products"
    assert script_ops[0].params == {"csv_file": "datas/products.csv"}


def test_python_script_legacy_style(recwarn):
    """Legacy file/method keys are deprecated but converted to handler."""
    config = {
        "Scripts": {
            "python_script": {
                "Import Products": {
                    "file": "scripts/products.py",
                    "method": "import_products",
                    "params": {},
                }
            }
        }
    }
    ops = build_plan(config)
    script_ops = [op for op in ops if isinstance(op, RunScript)]
    assert script_ops[0].handler == "scripts/products.py::import_products"


# ── Website ───────────────────────────────────────────────────────────────────

def test_website_theme_maps_to_install_modules():
    config = {"Website": {"website": {"theme": "theme_clean"}}}
    ops = build_plan(config)
    install_ops = [op for op in ops if isinstance(op, InstallModules)]
    assert any("theme_clean" in op.module_names for op in install_ops)


# ── Notifications ─────────────────────────────────────────────────────────────

def test_slack_section():
    config = {
        "Notify": {
            "slack": {
                "message": "Done!",
                "message_type": "valid",
            }
        }
    }
    ops = build_plan(config)
    slack_ops = [op for op in ops if isinstance(op, SendSlackMessage)]
    assert len(slack_ops) == 1
    assert slack_ops[0].message == "Done!"


def test_mattermost_section():
    config = {
        "Notify": {
            "mattermost": {
                "message": "Done!",
                "url": "https://mm.example.com/hook/abc",
            }
        }
    }
    ops = build_plan(config)
    mm_ops = [op for op in ops if isinstance(op, SendMattermostMessage)]
    assert len(mm_ops) == 1
    assert mm_ops[0].message == "Done!"


# ── Metadata keys skipped ─────────────────────────────────────────────────────

def test_metadata_keys_not_treated_as_sections():
    """Keys in _METADATA_KEYS must never be processed as section blocks."""
    config = {
        "name": "My Config",
        "version": "17.0",
        "auth": {"url": "http://localhost"},
        "Base": {"modules": ["sale"]},
    }
    ops = build_plan(config)
    # Only the real section "Base" should produce ops
    assert InstallModules(module_names=["sale"]) in ops
    assert len(ops) == 1


# ── Section ordering ──────────────────────────────────────────────────────────

def test_operations_ordered_within_section():
    """modules must appear before datas within the same section."""
    config = {
        "Base": {
            "modules": ["sale"],
            "datas": {
                "Partner": {"model": "res.partner", "name": "Test"}
            }
        }
    }
    ops = build_plan(config)
    module_idx = next(i for i, op in enumerate(ops) if isinstance(op, InstallModules))
    upsert_idx = next(i for i, op in enumerate(ops) if isinstance(op, UpsertRecord))
    assert module_idx < upsert_idx


def test_sections_ordered_by_yaml_insertion():
    """Operations from earlier sections precede those from later sections."""
    config = {
        "First": {"modules": ["sale"]},
        "Second": {"modules": ["purchase"]},
    }
    ops = build_plan(config)
    install_ops = [op for op in ops if isinstance(op, InstallModules)]
    assert install_ops[0].module_names == ["sale"]
    assert install_ops[1].module_names == ["purchase"]


# ── Empty / edge cases ────────────────────────────────────────────────────────

def test_empty_config():
    assert build_plan({}) == []


def test_section_with_no_recognised_directives():
    config = {"Empty": {"unknown_key": "value"}}
    assert build_plan(config) == []


def test_non_dict_section_skipped():
    config = {"scalar_key": "just a string"}
    assert build_plan(config) == []
