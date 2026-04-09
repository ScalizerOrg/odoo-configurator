# Copyright 2025 Scalizer (<https://www.scalizer.fr>)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

"""
Context — the dependency container passed to all executor functions and plugins.

Usage:
    ctx = Context(
        client=OdooClient(...),
        config=loaded_config,
        mode=["config"],
        secrets=SecretsProvider(),
        utils=Utils(base_path=Path(".")),
    )

    ctx.client.get_ref("base.EUR")
    ctx.secrets.resolve("env://MY_PASS")
    ctx.utils.resolve_path("datas/partners.csv")
    ctx.extra_clients["staging"].odoo.search_ids("res.partner", [])
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from odoo_configurator.client import OdooClient
    from odoo_configurator.secrets import SecretsProvider
    from odoo_configurator.utils import Utils

logger = logging.getLogger(__name__)


@dataclass
class Context:
    """
    All runtime dependencies bundled in one place.

    Attributes:
        client:        Primary OdooClient (wraps s6r_odoo, connects to the target Odoo).
        config:        The merged YAML config dict for the current execution.
        mode:          Active execution mode flags, e.g. ["install"] or ["config"].
        secrets:       SecretsProvider for resolving env:// and future bw:// URIs.
        utils:         Path resolution utilities, anchored to the project base_path.
        extra_clients: Named secondary Odoo connections (replaces setattr monkey-patching).
        sql_clients:   Named SQL connections (replaces setattr monkey-patching).
    """

    client: Any          # OdooClient — typed as Any to avoid circular imports at runtime
    config: dict
    mode: list[str]
    secrets: Any         # SecretsProvider
    utils: Any           # Utils
    extra_clients: dict[str, Any] = field(default_factory=dict)  # named secondary Odoo connections
    sql_clients: dict[str, Any] = field(default_factory=dict)    # named SQL connections

    def is_install_mode(self) -> bool:
        """Return True when running in install (first-run) mode."""
        return "install" in self.mode

    def is_config_mode(self) -> bool:
        """Return True when running in config (update) mode."""
        return "config" in self.mode

    def log(self, msg: str, *args: Any, level: int = logging.INFO) -> None:
        """Convenience logger delegating to the module-level logger."""
        logger.log(level, msg, *args)
