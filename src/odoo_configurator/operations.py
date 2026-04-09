# Copyright 2025 Scalizer (<https://www.scalizer.fr>)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

"""
Operation dataclasses — the vocabulary of everything the configurator can do.

The planner (planner.py) reads a YAML config dict and produces an ordered list
of these objects. The executor (executor.py) consumes that list and calls Odoo.
Nothing else in the codebase should call Odoo directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ── Module management ─────────────────────────────────────────────────────────

@dataclass
class InstallModules:
    """Install one or more Odoo modules (skips already-installed ones)."""
    module_names: list[str]


@dataclass
class UpdateModules:
    """Force an upgrade of one or more installed Odoo modules."""
    module_names: list[str]


@dataclass
class UninstallModules:
    """Uninstall one or more Odoo modules."""
    module_names: list[str]


# ── Settings & parameters ─────────────────────────────────────────────────────

@dataclass
class ApplySettings:
    """Write values to res.config.settings and execute them."""
    values: dict
    company_id: int | None = None
    context: dict = field(default_factory=dict)


@dataclass
class SetSystemParam:
    """Create or update an ir.config_parameter key/value pair."""
    key: str
    value: str


@dataclass
class SetFieldDefault:
    """Set an ir.default value for a model field."""
    model: str
    field: str
    value: object
    condition: str | None = None


# ── Record management ─────────────────────────────────────────────────────────

@dataclass
class UpsertRecord:
    """
    Create or update a single record.

    Lookup strategy (in priority order):
      1. force_id  — xml_id string (e.g. 'external_config.partner_1') or int db id
      2. search_key — field name(s) to search by (e.g. 'name' or 'name,ref')

    values may contain special field suffixes resolved by the executor:
      field/id     → many2one by xml_id
      field_ids/id → many2many by xml_id list
      field/json   → dict/list serialised to JSON string
    """
    model: str
    values: dict
    force_id: str | int | None = None
    search_key: str | None = None
    context: dict | None = None
    no_raise: bool = False
    languages: list[str] = field(default_factory=list)
    name: str = ""   # human-readable label (from YAML key) for logging


@dataclass
class LoadRecords:
    """
    Batch-load records using Odoo's load() API (faster than individual writes).
    All records share the same model; each entry in rows is a dict of values.
    """
    model: str
    rows: list[dict]
    context: dict = field(default_factory=dict)


@dataclass
class DeleteRecords:
    """Delete all records matching a domain."""
    model: str
    domain: list
    context: dict = field(default_factory=dict)


@dataclass
class DeleteRecord:
    """Delete a single record identified by xml_id."""
    model: str
    xml_id: str


@dataclass
class SetActive:
    """Activate or deactivate records matching a domain."""
    model: str
    domain: list
    active: bool
    search_value_xml_id: str | None = None


@dataclass
class UpdateByDomain:
    """Write values to all records matching a domain."""
    model: str
    domain: list
    values: dict
    search_value_xml_id: str | None = None
    context: dict = field(default_factory=dict)


# ── Method calls ─────────────────────────────────────────────────────────────

@dataclass
class CallMethod:
    """Call an arbitrary method on a model (env['model'].method(*args))."""
    model: str
    method: str
    args: list = field(default_factory=list)
    context: dict = field(default_factory=dict)
    no_raise: bool = False


@dataclass
class CallActionServer:
    """Run an ir.actions.server record."""
    action_xml_id: str
    model: str
    res_id: int | None = None
    context: dict = field(default_factory=dict)
    no_raise: bool = False


# ── Users & roles ─────────────────────────────────────────────────────────────

@dataclass
class UpsertUser:
    """Create or update a res.users record, including group assignments."""
    login: str
    values: dict = field(default_factory=dict)
    groups: list[str] = field(default_factory=list)   # xml_ids; 'unlink all' supported
    force_id: str | None = None
    context: dict = field(default_factory=dict)


@dataclass
class UpsertRole:
    """Create or update a res.users.role record (requires base_user_role module)."""
    name: str
    implied_ids: list[str] = field(default_factory=list)  # group xml_ids
    user_xml_ids: list[str] = field(default_factory=list)
    force_id: str | None = None


# ── Data integration (CSV / Python scripts) ───────────────────────────────────

@dataclass
class ImportCSV:
    """
    Import records from a CSV file using Odoo's load() API.
    handler: optional 'path/to/file.py::function_name' for custom import logic.
    """
    model: str
    file_path: str
    handler: str | None = None       # e.g. 'scripts/helpers.py::advanced_import_data'
    batch_size: int = 1000
    skip_lines: int = 0
    limit: int | None = None
    context: dict | None = None
    name_create_enabled_fields: list[str] = field(default_factory=list)
    ignore_fields: list[str] = field(default_factory=list)
    name: str = ""   # human-readable label for logging


@dataclass
class RunScript:
    """
    Execute a function from an external Python file.
    handler: 'path/to/file.py::function_name'
    The function receives (ctx, params) — no monkey-patching, no self tricks.
    """
    handler: str                     # e.g. 'scripts/import_products_v2.py::import_products_variants'
    params: dict = field(default_factory=dict)
    name: str = ""   # human-readable label for logging


# ── Translations ──────────────────────────────────────────────────────────────

@dataclass
class InstallTranslation:
    """Install a language pack into Odoo."""
    lang_code: str                   # e.g. 'fr_FR'


# ── Notifications ─────────────────────────────────────────────────────────────

@dataclass
class SendSlackMessage:
    """Send a message to a Slack channel."""
    message: str
    channel: str | None = None
    message_type: str = "valid"      # valid | error | warning | start
    title: str | None = None


@dataclass
class SendMattermostMessage:
    """Send a message to a Mattermost webhook."""
    message: str
    url: str | None = None
    channel: str | None = None


# ── Type alias for the full operation union ───────────────────────────────────

Operation = (
    InstallModules | UpdateModules | UninstallModules
    | ApplySettings | SetSystemParam | SetFieldDefault
    | UpsertRecord | LoadRecords | DeleteRecords | DeleteRecord
    | SetActive | UpdateByDomain
    | CallMethod | CallActionServer
    | UpsertUser | UpsertRole
    | ImportCSV | RunScript
    | InstallTranslation
    | SendSlackMessage | SendMattermostMessage
)
