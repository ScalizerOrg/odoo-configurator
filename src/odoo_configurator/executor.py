# Copyright 2025 Scalizer (<https://www.scalizer.fr>)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

"""
Executor — dispatches an ordered list of Operations to Odoo via the Context.

`execute_all(ops, ctx)` is the main entry point; it runs every Operation in order.
Each `_execute_*` function handles one Operation type.

Expression evaluation (get_ref, get_env_var, …) is done per-record so that a record
created by an earlier operation is immediately referenceable by a later one.

Plugin modules loaded via `load_plugin_function()` are cached so a file used multiple
times is exec'd only once.

Field name suffix conventions:
  field/id  (str)  → many2one: resolve xml_id to int
  field/id  (list) → many2many: resolve list of xml_ids to list of ints
  field/json       → serialize value to JSON string
  field.id         → synonym for field/id in create/write mode
"""

from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path
from typing import Any

from odoo_configurator.context import Context
from odoo_configurator.evaluator import make_eval_ns, resolve_dict
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

# Module cache for external Python plugin files: abs_path → loaded module
_plugin_cache: dict[str, Any] = {}


def execute_all(ops: list[Operation], ctx: Context) -> None:
    """Execute every Operation in *ops* sequentially against *ctx*."""
    ns = make_eval_ns(ctx.client, ctx.secrets, ctx.utils)
    for op in ops:
        _dispatch(op, ctx, ns)


def _dispatch(op: Operation, ctx: Context, ns: dict) -> None:
    """Route one Operation to its handler function."""
    match op:
        case InstallModules(module_names=names):
            _execute_install_modules(names, ctx)
        case UpdateModules(module_names=names):
            _execute_update_modules(names, ctx)
        case UninstallModules(module_names=names):
            _execute_uninstall_modules(names, ctx)
        case InstallTranslation(lang_code=lang):
            _execute_install_translation(lang, ctx)
        case SetSystemParam(key=key, value=value):
            _execute_set_system_param(key, value, ctx, ns)
        case ApplySettings() as s:
            _execute_apply_settings(s, ctx, ns)
        case SetFieldDefault() as d:
            _execute_set_field_default(d, ctx, ns)
        case UpsertRecord() as rec:
            _execute_upsert_record(rec, ctx, ns)
        case DeleteRecord(model=model, xml_id=xml_id):
            _execute_delete_record(model, xml_id, ctx)
        case DeleteRecords(model=model, domain=domain, context=dctx):
            _execute_delete_records(model, domain, dctx, ctx, ns)
        case UpsertUser() as u:
            _execute_upsert_user(u, ctx, ns)
        case UpsertRole() as r:
            _execute_upsert_role(r, ctx, ns)
        case CallMethod() as c:
            _execute_call_method(c, ctx, ns)
        case ImportCSV() as imp:
            _execute_import_csv(imp, ctx, ns)
        case RunScript() as script:
            _execute_run_script(script, ctx, ns)
        case SendSlackMessage() as msg:
            _execute_slack(msg, ctx, ns)
        case SendMattermostMessage() as msg:
            _execute_mattermost(msg, ctx, ns)
        case _:
            logger.warning("No executor for operation type: %s", type(op).__name__)


# ── Module management ─────────────────────────────────────────────────────────

def _execute_install_modules(names: list[str], ctx: Context) -> None:
    logger.info("Installing modules: %s", names)
    ctx.client.odoo.install_modules(names)


def _execute_update_modules(names: list[str], ctx: Context) -> None:
    logger.info("Updating modules: %s", names)
    ctx.client.odoo.update_modules(names)


def _execute_uninstall_modules(names: list[str], ctx: Context) -> None:
    logger.info("Uninstalling modules: %s", names)
    ctx.client.odoo.uninstall_modules(names)


def _execute_install_translation(lang: str, ctx: Context) -> None:
    logger.info("Installing translation: %s", lang)
    ctx.client.odoo.execute_kw(
        "base.language.install", "create",
        [{"lang": lang, "overwrite": False}],
    )
    # Load the language
    ctx.client.odoo.execute_kw(
        "base.language.install", "lang_install",
        [[]],
        {"context": {"lang": lang}},
    )


# ── Settings & parameters ─────────────────────────────────────────────────────

def _execute_set_system_param(key: str, value: str, ctx: Context, ns: dict) -> None:
    logger.info("Setting system parameter: %s", key)
    resolved_value = resolve_dict({"v": value}, ns)["v"]
    odoo = ctx.client.odoo
    existing = odoo.search_ids("ir.config_parameter", [("key", "=", key)])
    if existing:
        odoo.write("ir.config_parameter", existing, {"value": str(resolved_value)})
    else:
        odoo.create("ir.config_parameter", {"key": key, "value": str(resolved_value)})


def _execute_apply_settings(op: ApplySettings, ctx: Context, ns: dict) -> None:
    logger.info("Applying settings (company_id=%s)", op.company_id)
    values = resolve_dict(op.values, ns)
    context = dict(ctx.client.context)
    if op.company_id:
        context["allowed_company_ids"] = [op.company_id]
    if op.context:
        context.update(op.context)
    odoo = ctx.client.odoo
    rec_id = odoo.create("res.config.settings", values, context=context)
    odoo.execute_kw("res.config.settings", "execute", [[rec_id]], {"context": context})


def _execute_set_field_default(op: SetFieldDefault, ctx: Context, ns: dict) -> None:
    logger.info("Setting default: %s.%s", op.model, op.field)
    value = resolve_dict({"v": op.value}, ns)["v"]
    odoo = ctx.client.odoo
    existing = odoo.search_ids(
        "ir.default",
        [("field_id.model", "=", op.model), ("field_id.name", "=", op.field)],
    )
    vals: dict = {
        "field_id": _get_field_id(op.model, op.field, odoo),
        "json_value": json.dumps(value),
    }
    if op.condition:
        vals["condition"] = op.condition
    if existing:
        odoo.write("ir.default", existing, vals)
    else:
        odoo.create("ir.default", vals)


def _get_field_id(model: str, field_name: str, odoo: Any) -> int:
    ids = odoo.search_ids(
        "ir.model.fields",
        [("model", "=", model), ("name", "=", field_name)],
    )
    if not ids:
        raise ValueError(f"Field '{field_name}' not found on model '{model}'")
    return ids[0]


# ── Records ───────────────────────────────────────────────────────────────────

def _execute_upsert_record(op: UpsertRecord, ctx: Context, ns: dict) -> None:
    logger.info("\t* %s (%s)", op.name or op.force_id or op.search_key, op.model)
    odoo = ctx.client.odoo
    context = dict(ctx.client.context)
    if op.context:
        context.update(op.context)

    # Resolve get_* expressions in values
    values = resolve_dict(op.values, ns)

    # Resolve field suffixes
    values = _resolve_field_suffixes(values, ctx, use_load=bool(op.force_id and isinstance(op.force_id, str)))

    # Find or absent existing record id(s)
    object_ids: list[int] | int | None = None
    use_load = False  # whether to use Odoo's load() API

    if op.force_id and isinstance(op.force_id, str):
        force_id = op.force_id
        if "." not in force_id:
            force_id = f"external_config.{force_id}"
        values["id"] = force_id
        use_load = True
        existing = odoo.get_id_from_xml_id(force_id, no_raise=True)
        object_ids = existing or None

    elif op.force_id and isinstance(op.force_id, int):
        object_ids = op.force_id

    elif op.search_key:
        domain = [(op.search_key, "=", values.get(op.search_key))]
        results = odoo.search_ids(op.model, domain)
        object_ids = results[0] if results else None

    else:
        logger.warning("UpsertRecord '%s' has no force_id or search_key — skipped.", op.name)
        return

    # Handle special post-upsert function call
    function = values.pop("__function__", None)

    if use_load:
        # Use Odoo's load() API (faster for large sets, works with xml_id references)
        _load_record(op.model, values, context, odoo, op.name)
    else:
        for lang in (op.languages or [context.get("lang", "en_US")]):
            lang_context = {**context, "lang": lang}
            if object_ids:
                odoo.write(op.model, [object_ids] if isinstance(object_ids, int) else object_ids,
                           {k: v for k, v in values.items() if k != "id"},
                           context=lang_context)
            else:
                new_id = odoo.create(op.model, {k: v for k, v in values.items() if k != "id"},
                                     context=lang_context)
                object_ids = new_id

    if function and object_ids:
        _call_record_function(function, op.model, object_ids, context, odoo)


def _resolve_field_suffixes(values: dict, ctx: Context, use_load: bool) -> dict:
    """
    Expand /id, .id, /id list, and /json field name conventions.

    In load() mode (use_load=True):  field/id → field.id (dot notation for load())
    In write() mode (use_load=False): field/id → field (plain int)
    """
    resolved = {}
    for key, value in values.items():
        if key == "__function__":
            resolved[key] = value
            continue

        if key.endswith("/id"):
            base = key[:-3]
            if isinstance(value, list):
                # many2many: list of xml_ids
                if use_load:
                    new_key = base + ".ids"
                    resolved[new_key] = ",".join(
                        str(ctx.client.get_ref(v)) if "." in str(v) else str(v)
                        for v in value
                    )
                else:
                    resolved[base] = [(6, 0, [ctx.client.get_ref(v) for v in value])]
            elif isinstance(value, str) and "." in value:
                # many2one: single xml_id
                if use_load:
                    resolved[base + ".id"] = value  # keep as xml_id string for load()
                else:
                    resolved[base] = ctx.client.get_ref(value)
            else:
                resolved[key] = value
        elif key.endswith(".id") and not use_load:
            base = key[:-3]
            resolved[base] = value
        elif key.endswith("/json"):
            base = key[:-5]
            resolved[base] = json.dumps(value) if not isinstance(value, str) else value
        else:
            resolved[key] = value
    return resolved


def _load_record(model: str, values: dict, context: dict, odoo: Any, name: str) -> None:
    """Write one record via Odoo's load() API."""
    load_keys = list(values.keys())
    load_data = []
    for k in load_keys:
        v = values[k]
        load_data.append(str(v) if isinstance(v, bool) else v)
    result = odoo.execute_kw(
        model, "load",
        [load_keys, [load_data]],
        {"context": context},
    )
    for msg in (result or {}).get("messages", []):
        logger.error("%s load error [%s]: %s", name, msg.get("record"), msg.get("message"))


def _call_record_function(function: str, model: str, rec_ids: Any, context: dict, odoo: Any) -> None:
    """Call a model method on the just-upserted record (legacy 'function' key)."""
    if isinstance(rec_ids, int):
        rec_ids = [rec_ids]
    odoo.execute_kw(model, function, [rec_ids], {"context": context})


def _execute_delete_record(model: str, xml_id: str, ctx: Context) -> None:
    logger.info("Deleting record %s (%s)", xml_id, model)
    rec_id = ctx.client.odoo.get_id_from_xml_id(xml_id, no_raise=True)
    if rec_id:
        ctx.client.odoo.execute_kw(model, "unlink", [[rec_id]])


def _execute_delete_records(
    model: str,
    domain: list,
    op_context: dict | None,
    ctx: Context,
    ns: dict,
) -> None:
    from odoo_configurator.evaluator import eval_domain
    resolved_domain = eval_domain(domain, ns)
    logger.info("Deleting records matching domain on %s", model)
    context = dict(ctx.client.context)
    if op_context:
        context.update(op_context)
    ids = ctx.client.odoo.search_ids(model, resolved_domain)
    if ids:
        ctx.client.odoo.execute_kw(model, "unlink", [ids], {"context": context})


# ── Users ─────────────────────────────────────────────────────────────────────

def _execute_upsert_user(op: UpsertUser, ctx: Context, ns: dict) -> None:
    logger.info("Upserting user: %s", op.login)
    odoo = ctx.client.odoo
    values = resolve_dict(op.values, ns)
    context = dict(ctx.client.context)
    if op.context:
        context.update(op.context)

    existing = odoo.search_ids("res.users", [("login", "=", op.login)])
    if existing:
        rec_id = existing[0]
        odoo.write("res.users", [rec_id], values, context=context)
    else:
        values["login"] = op.login
        rec_id = odoo.create("res.users", values, context=context)

    if op.groups:
        _apply_user_groups(rec_id, op.groups, ctx)


def _apply_user_groups(user_id: int, groups: list[str], ctx: Context) -> None:
    """Set user group memberships from a list of xml_ids."""
    odoo = ctx.client.odoo
    group_ids = [ctx.client.get_ref(g) for g in groups if g != "unlink all"]
    if "unlink all" in groups:
        odoo.write("res.users", [user_id], {"groups_id": [(5, 0, 0)]})
    if group_ids:
        odoo.write("res.users", [user_id], {"groups_id": [(6, 0, group_ids)]})


# ── Roles ─────────────────────────────────────────────────────────────────────

def _execute_upsert_role(op: UpsertRole, ctx: Context, ns: dict) -> None:
    logger.info("Upserting role: %s", op.name)
    odoo = ctx.client.odoo
    implied_ids = [(6, 0, [ctx.client.get_ref(g) for g in op.implied_ids])]
    user_ids = [ctx.client.get_ref(u) for u in op.user_xml_ids]
    line_ids = [(0, 0, {"user_id": uid}) for uid in user_ids]

    values: dict = {"name": op.name, "implied_ids": implied_ids}
    if line_ids:
        values["line_ids"] = [(5, 0, 0)] + line_ids

    if op.force_id:
        force_id = op.force_id
        if "." not in force_id:
            force_id = f"external_config.{force_id}"
        values["id"] = force_id
        existing = odoo.get_id_from_xml_id(force_id, no_raise=True)
    else:
        existing = odoo.search_ids("res.users.role", [("name", "=", op.name)])
        existing = existing[0] if existing else None

    if existing:
        odoo.write("res.users.role", [existing], {k: v for k, v in values.items() if k != "id"})
    elif op.force_id:
        _load_record("res.users.role", values, dict(ctx.client.context), odoo, op.name)
    else:
        odoo.create("res.users.role", {k: v for k, v in values.items() if k != "id"})


# ── Method calls ──────────────────────────────────────────────────────────────

def _execute_call_method(op: CallMethod, ctx: Context, ns: dict) -> None:
    logger.info("Calling %s.%s()", op.model, op.method)
    context = dict(ctx.client.context)
    if op.context:
        context.update(op.context)
    try:
        ctx.client.odoo.execute_kw(
            op.model, op.method,
            [op.args],
            {"context": context},
        )
    except Exception as e:
        if op.no_raise:
            logger.error("CallMethod %s.%s failed (no_raise): %s", op.model, op.method, e)
        else:
            raise


# ── CSV imports ───────────────────────────────────────────────────────────────

def _execute_import_csv(op: ImportCSV, ctx: Context, ns: dict) -> None:
    logger.info("Importing CSV '%s' → %s", op.name, op.model)
    resolved_path = ctx.utils.resolve_path(op.file_path)
    context = dict(ctx.client.context)
    if op.context:
        context.update(op.context)

    if op.handler:
        # Custom handler: file.py::function(ctx, file_path, model, params)
        func = load_plugin_function(op.handler, ctx)
        params = {
            "batch_size": op.batch_size,
            "skip_lines": op.skip_lines,
            "limit": op.limit,
            "ignore_fields": op.ignore_fields,
            "name_create_enabled_fields": op.name_create_enabled_fields,
            "context": context,
        }
        func(ctx, resolved_path, op.model, params)
    else:
        # Default: use s6r_odoo's load_batch
        ctx.client.odoo.load_batch(
            op.model,
            resolved_path,
            batch_size=op.batch_size,
            skip_lines=op.skip_lines,
            limit=op.limit,
            ignore_fields=op.ignore_fields,
            context=context,
        )


# ── Python scripts ────────────────────────────────────────────────────────────

def _execute_run_script(op: RunScript, ctx: Context, ns: dict) -> None:
    logger.info("Running script '%s'", op.name or op.handler)
    func = load_plugin_function(op.handler, ctx)
    resolved_params = resolve_dict(op.params, ns) if op.params else {}
    func(ctx, resolved_params)


# ── Notifications ─────────────────────────────────────────────────────────────

def _execute_slack(op: SendSlackMessage, ctx: Context, ns: dict) -> None:
    try:
        from slack_sdk import WebClient
    except ImportError:
        logger.warning("slack_sdk not installed — Slack notification skipped.")
        return
    token = ctx.secrets.resolve(ctx.config.get("slack_token", ""))
    if not token:
        logger.warning("No slack_token configured — Slack notification skipped.")
        return
    channel = op.channel or ctx.config.get("slack_channel", "")
    client = WebClient(token=token)
    client.chat_postMessage(channel=channel, text=op.message)


def _execute_mattermost(op: SendMattermostMessage, ctx: Context, ns: dict) -> None:
    url = op.url or ctx.config.get("mattermost_url", "")
    channel = op.channel or ctx.config.get("mattermost_channel", "")
    if not url:
        logger.warning("No mattermost URL — Mattermost notification skipped.")
        return
    import requests
    payload = {"text": op.message}
    if channel:
        payload["channel"] = channel
    try:
        requests.post(url, json=payload, timeout=10).raise_for_status()
    except Exception as e:
        logger.error("Mattermost notification failed: %s", e)


# ── Plugin loader ─────────────────────────────────────────────────────────────

def load_plugin_function(handler: str, ctx: Context) -> Any:
    """
    Load a function from 'path/to/file.py::function_name'.

    The file is resolved via ctx.utils.resolve_path().
    Modules are cached so a file used multiple times is exec'd only once.
    """
    if "::" not in handler:
        raise ValueError(
            f"Invalid handler '{handler}'. Expected format: 'path/to/file.py::function_name'"
        )
    file_part, func_name = handler.split("::", 1)
    resolved_path = str(Path(ctx.utils.resolve_path(file_part)).resolve())

    if resolved_path not in _plugin_cache:
        stem = Path(resolved_path).stem
        spec = importlib.util.spec_from_file_location(stem, resolved_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load plugin file: {resolved_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _plugin_cache[resolved_path] = module

    module = _plugin_cache[resolved_path]
    if not hasattr(module, func_name):
        raise AttributeError(
            f"Plugin '{resolved_path}' has no function '{func_name}'. "
            f"Available: {[n for n in dir(module) if not n.startswith('_')]}"
        )
    return getattr(module, func_name)
