# Copyright 2025 Scalizer (<https://www.scalizer.fr>)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

"""
Expression evaluator — resolves dynamic `get_*` expressions in YAML values.

The callable functions available in YAML are an explicit dict (the namespace).
resolve_value is a pure function: given a value and a namespace it returns the
resolved result with no side effects. Resolution happens per-record in the executor
so a record created in step N can be referenced with get_ref() in step N+1.

__builtins__ is set to {} so arbitrary Python cannot be executed from YAML.
Only explicitly whitelisted names in the namespace are callable.

The 'o' key in the namespace enables the legacy nested call syntax o.get_ref(...)
for backward compatibility.
"""

from __future__ import annotations

import logging
from ast import literal_eval
from typing import Any

logger = logging.getLogger(__name__)

# Sentinel — nothing was provided (distinct from None, which is a valid value)
_MISSING = object()


def make_eval_ns(client: Any, secrets: Any, utils: Any) -> dict:
    """
    Build the evaluation namespace exposed to YAML `get_*` expressions.

    Parameters map directly to the methods callers can use in YAML values.
    Adding a new callable here is the *only* change needed to expose it in YAML.

    Args:
        client:  OdooClient instance  (provides get_ref, get_record, etc.)
        secrets: SecretsProvider      (provides get_env_var)
        utils:   Utils                (provides get_file_full_path)
    """
    ns: dict[str, Any] = {
        # ── Odoo lookups ─────────────────────────────────────────────────────
        "get_ref":            client.get_ref,
        "get_record":         client.get_record,
        "get_search_id":      client.get_search_id,
        "get_country":        client.get_country,
        "get_menu":           client.get_menu,
        "get_image_url":      client.get_image_url,
        "get_image_local":    client.get_image_local,
        "get_local_file":     client.get_local_file,
        "get_xml_id_from_id": client.get_xml_id_from_id,
        "get_default":        client.default_get,

        # ── Environment / secrets ─────────────────────────────────────────────
        # LEGACY: get_env_var() — use env://VAR_NAME URI in new configs
        "get_env_var":        secrets.get_env_var,

        # ── Nested call support ───────────────────────────────────────────────
        # LEGACY: 'o.get_ref(...)' syntax in customer YAML files.
        # 'o' is the client object; its get_* methods are accessible as o.method().
        "o":                  client,

        # ── Builtins disabled for safety ─────────────────────────────────────
        "__builtins__":       {},
    }
    return ns


def resolve_value(value: Any, ns: dict) -> Any:
    """
    Resolve a single YAML value against the evaluation namespace.

    - Strings starting with 'get_' are evaluated as Python expressions.
    - All other values are returned unchanged.
    - Raises NameError if a get_* function is not in the namespace.
    """
    if not isinstance(value, str):
        return value
    if not value.startswith("get_"):
        return value
    logger.debug("Evaluating expression: %s", value)
    try:
        return eval(value, ns)  # noqa: S307 — namespace is explicitly restricted
    except NameError as e:
        raise NameError(
            f"Unknown function in YAML expression: {value!r}.\n"
            f"Available get_* functions: "
            f"{[k for k in ns if k.startswith('get_')]}"
        ) from e


def resolve_dict(d: dict, ns: dict) -> dict:
    """Resolve all get_* expressions in the top-level values of a dict."""
    return {k: resolve_value(v, ns) for k, v in d.items()}


def resolve_deep(value: Any, ns: dict) -> Any:
    """
    Recursively resolve get_* expressions throughout a nested structure
    (dict, list, or scalar).

    Used for structured values like function params, domain lists, etc.
    For flat record values, prefer resolve_dict (cheaper).
    """
    if isinstance(value, dict):
        return {k: resolve_deep(v, ns) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_deep(item, ns) for item in value]
    return resolve_value(value, ns)


def eval_domain(domain: str | list, ns: dict) -> list:
    """
    Evaluate a domain that may be:
      - Already a list   → resolve any get_* in leaf values
      - A string literal → parse with literal_eval, then resolve
      - A string with get_* → evaluate the whole thing

    Examples:
      "[('name', '=', 'foo')]"             → parsed as list
      "[('id', '=', get_ref('base.EUR'))]" → evaluated via ns
    """
    if isinstance(domain, list):
        return resolve_deep(domain, ns)
    if isinstance(domain, str):
        if domain.startswith("get_"):
            return resolve_value(domain, ns)
        if "get_" in domain:
            # Domain contains embedded get_* calls — literal_eval can't handle these.
            return eval(domain, ns)  # noqa: S307 — namespace is explicitly restricted
        # Pure literal (no get_* expressions) — safe to parse without eval.
        parsed = literal_eval(domain)
        return resolve_deep(parsed, ns)
    raise TypeError(f"Domain must be a list or string, got {type(domain)}: {domain!r}")
