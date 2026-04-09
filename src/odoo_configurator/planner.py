# Copyright 2025 Scalizer (<https://www.scalizer.fr>)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

"""
Planner — walks a merged config dict and produces an ordered list of Operations.

Design:
  - The planner is a pure function: given a config dict and a mode list it returns
    a list of Operation objects. No Odoo calls, no side effects.
  - Every YAML directive has one place where it is recognised and converted to an
    Operation. Adding a new directive means: (1) add an Operation dataclass to
    operations.py, (2) add a clause here in _emit_section().

Section iteration:
  The config dict is structured as metadata keys (name, version, auth, …) plus
  user-defined section blocks (dicts). Every section block is walked, and any
  recognised directive key inside it produces Operations.

Operation ordering within a section:
    1. modules / updates / uninstall_modules
    2. translations
    3. system_parameter
    4. config (settings)
    5. datas / datas_roles / defaults
    6. users
    7. call
    8. import_data
    9. python_script / script (alias)

The above order is fixed. Operations from earlier sections are emitted before later
sections — sections are processed in YAML insertion order.
"""

from __future__ import annotations

import logging
from typing import Any

from odoo_configurator.operations import (
    ApplySettings,
    CallMethod,
    DeleteRecord,
    DeleteRecords,
    ImportCSV,
    InstallModules,
    InstallTranslation,
    Operation,
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

logger = logging.getLogger(__name__)

# Keys that are configuration metadata, not section blocks.
# Section blocks are any top-level dict key NOT in this set.
_METADATA_KEYS = frozenset({
    "name", "version", "description",
    "auth", "http_auth",
    "includes", "inherits",          # inherits is the deprecated alias for includes
    "sequence", "script_files",      # script_files is the deprecated alias for sequence
    "configurator_version",
    "languages",
    # Slack / Mattermost config lives at the top level, not inside sections
    "slack", "slack_token", "slack_channel", "no_notification",
    "mattermost_channel", "mattermost_url",
    "install_mode",
})


def build_plan(config: dict, mode: list[str] | None = None) -> list[Operation]:
    """
    Walk *config* and return an ordered list of Operations.

    Args:
        config: Merged YAML config dict (from ConfigLoader.load_merged or similar).
        mode:   Execution mode flags, e.g. ["install"] or ["config"].
                Defaults to ["config"].

    Returns:
        Ordered list of Operations ready for the executor.
    """
    if mode is None:
        mode = ["config"]

    ops: list[Operation] = []

    # Top-level non-section directives
    _emit_top_level(config, mode, ops)

    # Section blocks
    for section_name, section in config.items():
        if section_name in _METADATA_KEYS:
            continue
        if not isinstance(section, dict):
            continue
        logger.debug("Planning section: %s", section_name)
        _emit_section(section_name, section, config, mode, ops)

    return ops


# ── Top-level directives (not inside a section block) ────────────────────────

def _emit_top_level(config: dict, mode: list[str], ops: list[Operation]) -> None:
    """Emit Operations for keys that live at the top level (not in sections)."""
    # translations: top-level list of language codes
    if "translations" in config:
        langs = config["translations"]
        if isinstance(langs, list):
            for lang in langs:
                ops.append(InstallTranslation(lang_code=lang))

    # Slack / Mattermost start notification — emitted once at the beginning
    # (handled by executor via config metadata, not an Operation)


# ── Section-level directive emitters ─────────────────────────────────────────

def _emit_section(
    section_name: str,
    section: dict,
    config: dict,
    mode: list[str],
    ops: list[Operation],
) -> None:
    """Emit all Operations from one section block, in the canonical order."""
    languages = section.get("languages") or config.get("languages")

    # 1. Modules
    if "modules" in section:
        module_list = _normalise_module_list(section["modules"])
        ops.append(InstallModules(module_names=module_list))

    if "updates" in section:
        module_list = _normalise_module_list(section["updates"])
        ops.append(UpdateModules(module_names=module_list))

    if "uninstall_modules" in section:
        module_list = _normalise_module_list(section["uninstall_modules"])
        ops.append(UninstallModules(module_names=module_list))

    # 2. Translations (section-level — rare but supported)
    if "translations" in section:
        langs = section["translations"]
        if isinstance(langs, list):
            for lang in langs:
                ops.append(InstallTranslation(lang_code=lang))

    # 3. System parameters
    if "system_parameter" in section:
        for key, value in section["system_parameter"].items():
            ops.append(SetSystemParam(key=key, value=str(value)))

    # 4. Settings (config)
    if "config" in section:
        raw = section["config"]
        company_id = raw.pop("company_id", None)  # extracted before passing values
        allowed = raw.pop("allowed_company_ids", None)
        ctx_override = raw.pop("context", None)
        values = dict(raw)
        if allowed is not None:
            values["allowed_company_ids"] = allowed
        ops.append(ApplySettings(
            values=values,
            company_id=company_id,
            context=ctx_override,
        ))

    # 5a. Datas records
    if "datas" in section:
        for record_name, record in section["datas"].items():
            if not isinstance(record, dict):
                continue
            op = _record_to_upsert(record_name, record, languages)
            if op is not None:
                ops.append(op)

    # 5b. Roles
    if "datas_roles" in section:
        for role_name, role_cfg in section["datas_roles"].items():
            if not isinstance(role_cfg, dict):
                continue
            ops.append(_role_to_op(role_name, role_cfg))

    # 5c. Field defaults
    if "defaults" in section:
        for _label, default_cfg in section["defaults"].items():
            if not isinstance(default_cfg, dict):
                continue
            ops.append(SetFieldDefault(
                model=default_cfg["model"],
                field=default_cfg["field"],
                value=default_cfg.get("value"),
                condition=default_cfg.get("condition"),
            ))

    # 6. Users
    if "users" in section:
        for login_key, user_cfg in section["users"].items():
            if not isinstance(user_cfg, dict):
                continue
            ops.append(_user_to_op(login_key, user_cfg))

    # 7. Calls
    if "call" in section:
        for _label, call_cfg in section["call"].items():
            if not isinstance(call_cfg, dict):
                continue
            ops.append(CallMethod(
                model=call_cfg["model"],
                method=call_cfg["method"],
                args=call_cfg.get("args", []),
                context=call_cfg.get("context"),
                no_raise=call_cfg.get("no_raise", False),
            ))

    # 8. CSV imports
    if "import_data" in section:
        for import_name, import_cfg in section["import_data"].items():
            if not isinstance(import_cfg, dict):
                continue
            # Build handler string from legacy keys if new key not present
            handler = import_cfg.get("handler")
            if handler is None and import_cfg.get("specific_import"):
                # LEGACY: specific_import + specific_method → handler: file.py::method
                legacy_file = import_cfg["specific_import"]
                legacy_method = import_cfg.get("specific_method", "")
                handler = f"{legacy_file}::{legacy_method}" if legacy_method else None
                if handler:
                    logger.warning(
                        "import_data '%s': 'specific_import'/'specific_method' are deprecated."
                        " Use 'handler: %s' instead.",
                        import_name,
                        handler,
                    )
            ops.append(ImportCSV(
                model=import_cfg["model"],
                file_path=import_cfg["file_path"],
                handler=handler,
                batch_size=import_cfg.get("batch_size", 50),
                skip_lines=import_cfg.get("skip_lines", 0),
                limit=import_cfg.get("limit"),
                context=import_cfg.get("context"),
                name_create_enabled_fields=import_cfg.get("name_create_enabled_fields", []),
                ignore_fields=import_cfg.get("ignore_fields", []),
                name=import_name,
            ))

    # 9. Python scripts (new 'script' key, legacy 'python_script' key)
    for script_key in ("script", "python_script"):
        if script_key in section:
            for script_name, script_cfg in section[script_key].items():
                if not isinstance(script_cfg, dict):
                    continue
                # New style: handler: file.py::function
                # Legacy style: file: + method:
                handler = script_cfg.get("handler")
                if handler is None:
                    legacy_file = script_cfg.get("file", "")
                    legacy_method = script_cfg.get("method", "")
                    if legacy_file and legacy_method:
                        handler = f"{legacy_file}::{legacy_method}"
                        logger.warning(
                            "python_script '%s': 'file'/'method' keys are deprecated."
                            " Use 'handler: %s' instead.",
                            script_name,
                            handler,
                        )
                ops.append(RunScript(
                    handler=handler or "",
                    params=script_cfg.get("params", {}),
                    name=script_name,
                ))

    # 10. Website theme — maps to InstallModules
    if "website" in section:
        website_cfg = section["website"]
        if isinstance(website_cfg, dict) and "theme" in website_cfg:
            ops.append(InstallModules(module_names=[website_cfg["theme"]]))

    # 11. Slack / Mattermost notifications inside a section
    if "slack" in section:
        slack_cfg = section["slack"]
        if isinstance(slack_cfg, dict):
            ops.append(SendSlackMessage(
                message=slack_cfg.get("message", ""),
                channel=slack_cfg.get("channel"),
                message_type=slack_cfg.get("message_type", "valid"),
                title=slack_cfg.get("title"),
            ))

    if "mattermost" in section:
        mm_cfg = section["mattermost"]
        if isinstance(mm_cfg, dict):
            ops.append(SendMattermostMessage(
                message=mm_cfg.get("message", ""),
                url=mm_cfg.get("url"),
                channel=mm_cfg.get("channel"),
            ))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalise_module_list(raw: list | str) -> list[str]:
    """Accept ['mod_a', 'mod_b'] or 'mod_a' and return a flat list of strings."""
    if isinstance(raw, str):
        return [raw]
    result = []
    for item in raw:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            # Module entry with extra keys: {name: 'sale', on_install_only: True}
            # on_install_only is ignored for now (deferred feature)
            name = item.get("name")
            if name:
                result.append(name)
    return result


def _record_to_upsert(
    record_name: str,
    record: dict,
    section_languages: list[str] | None,
) -> UpsertRecord | DeleteRecord | None:
    """Convert a datas record dict to an UpsertRecord (or DeleteRecord) Operation."""
    model = record.get("model")
    if not model:
        logger.warning("datas record '%s' has no 'model' key — skipped.", record_name)
        return None

    # delete: True means delete by force_id
    if record.get("delete"):
        return DeleteRecord(model=model, xml_id=record.get("force_id", record_name))

    # Collect all values that aren't structural keys
    _structural = {
        "model", "force_id", "search_key", "context", "no_raise",
        "languages", "delete", "function", "load",
    }
    values = {k: v for k, v in record.items() if k not in _structural}

    # Handle the 'function' key (call a method on the record after upsert)
    # This is preserved in values as a special key for the executor to handle.
    if "function" in record:
        values["__function__"] = record["function"]

    langs = record.get("languages") or section_languages

    return UpsertRecord(
        model=model,
        values=values,
        force_id=record.get("force_id"),
        search_key=record.get("search_key"),
        context=record.get("context"),
        no_raise=record.get("no_raise", False),
        languages=langs or [],
        name=record_name,
    )


def _role_to_op(role_name: str, role_cfg: dict) -> UpsertRole:
    """Convert a datas_roles entry to an UpsertRole Operation."""
    values = role_cfg.get("values", {})
    return UpsertRole(
        name=values.get("name", role_name),
        implied_ids=values.get("implied_ids", []),
        user_xml_ids=_extract_user_xml_ids(values.get("line_ids", [])),
        force_id=role_cfg.get("force_id"),
    )


def _extract_user_xml_ids(line_ids: list) -> list[str]:
    """Extract user xml_ids from role line_ids structure."""
    result = []
    for line in line_ids:
        if isinstance(line, dict):
            xml_id = line.get("user_id") or line.get("xml_id")
            if xml_id:
                result.append(str(xml_id))
        elif isinstance(line, str):
            result.append(line)
    return result


def _user_to_op(login_key: str, user_cfg: dict) -> UpsertUser:
    """Convert a users entry to an UpsertUser Operation."""
    login = user_cfg.get("login", login_key)
    values = user_cfg.get("values", {})
    groups = user_cfg.get("groups_id", [])
    return UpsertUser(
        login=login,
        values=values,
        groups=groups,
        force_id=user_cfg.get("force_id"),
        context=user_cfg.get("context"),
    )
