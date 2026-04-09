# Copyright 2025 Scalizer (<https://www.scalizer.fr>)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

"""
odoo-configurator CLI entry point.

Usage examples:

  # Single file (sequence: inside the file controls execution order):
  odoo-configurator config/main.yml

  # Multiple files merged in order (environment overlay pattern):
  odoo-configurator config/base.yml config/prod.yml

  # With target file (auth kept separate from config):
  odoo-configurator --target prod config/main.yml

Target file (targets.yml):
  version: 17.0
  targets:
    local:
      url: http://odoo.localhost
      db: my_db
      user: admin
      password: admin
    prod:
      url: https://prod.example.com
      db: prod-123
      password: env://ODOO_PROD_PASSWORD
"""

from __future__ import annotations

import argparse
import importlib.metadata
import logging
import sys
from pathlib import Path

try:
    __version__ = importlib.metadata.version("odoo-configurator")
except importlib.metadata.PackageNotFoundError:
    # Running from source without installation
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            tomllib = None  # type: ignore[assignment]

    if tomllib is not None:
        _pyproject = Path(__file__).parent.parent.parent / "pyproject.toml"
        if _pyproject.is_file():
            with open(_pyproject, "rb") as _f:
                __version__ = tomllib.load(_f).get("project", {}).get("version", "dev")
        else:
            __version__ = "dev"
    else:
        __version__ = "dev"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="odoo-configurator",
        description="Configure and update Odoo databases from YAML files.",
    )
    parser.add_argument(
        "paths",
        metavar="FILE",
        nargs="+",
        help="YAML config file(s) to load (merged in order)",
    )
    parser.add_argument(
        "--target",
        metavar="TARGET",
        help="Target name from targets.yml (auth kept in a separate file)",
    )
    parser.add_argument(
        "--targets-file",
        metavar="FILE",
        default="targets.yml",
        help="Path to the targets file (default: targets.yml)",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install mode — first-time setup, enables on_install_only operations",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable DEBUG logging",
    )
    parser.add_argument(
        "--debug-xmlrpc",
        action="store_true",
        help="Enable XML-RPC call logging",
    )
    parser.add_argument(
        "--lang",
        default="fr_FR",
        help="Language code for the Odoo context (default: fr_FR)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"odoo-configurator {__version__}",
    )
    args = parser.parse_args()

    # ── Logging setup ────────────────────────────────────────────────────────
    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)-8s %(name)s %(message)s")
    logger = logging.getLogger("odoo_configurator")
    logger.info("odoo-configurator %s", __version__)

    # ── Execution mode ───────────────────────────────────────────────────────
    mode = ["install", "config"] if args.install else ["config"]

    # ── Build paths list ─────────────────────────────────────────────────────
    config_paths = [Path(p) for p in args.paths]
    for p in config_paths:
        if not p.is_file():
            logger.error("Config file not found: %s", p)
            sys.exit(1)

    # ── Load configuration ───────────────────────────────────────────────────
    from odoo_configurator.loader import ConfigLoader
    from odoo_configurator.secrets import SecretsProvider
    from odoo_configurator.client import OdooClient
    from odoo_configurator.utils import Utils
    from odoo_configurator.context import Context
    from odoo_configurator.planner import build_plan
    from odoo_configurator.executor import execute_all

    # Base path for file resolution = directory of the first config file
    base_path = config_paths[0].parent.resolve()
    loader = ConfigLoader(search_dirs=[base_path])

    # Load configs — expands sequence: into ordered steps, resolves includes: via merge
    configs = loader.load_for_planning(config_paths)

    # Check version requirement against the root config
    loader.check_configurator_version(configs[0], __version__)

    # Use the root config for auth / metadata resolution
    config = configs[0]

    # ── Resolve authentication ───────────────────────────────────────────────
    secrets = SecretsProvider()

    if args.target:
        auth = _load_target(args.targets_file, args.target, secrets)
    else:
        raw_auth = config.get("auth", {})
        auth = _resolve_auth(raw_auth, secrets)

    if not auth.get("url") or not auth.get("db"):
        logger.error(
            "No authentication configured. Add an 'auth:' block to your config or use --target."
        )
        sys.exit(1)

    # ── Connect to Odoo ───────────────────────────────────────────────────────
    logger.info("Connecting to %s (db: %s, user: %s)", auth["url"], auth["db"], auth.get("user", "admin"))
    client = OdooClient(
        url=auth["url"],
        db=auth["db"],
        user=auth.get("user", "admin"),
        password=auth.get("password", ""),
        version=float(config.get("version", auth.get("version", 17.0))),
        http_user=auth.get("http_user"),
        http_password=auth.get("http_password"),
        lang=args.lang,
        debug_xmlrpc=args.debug_xmlrpc,
    )
    utils = Utils(base_path=base_path)

    ctx = Context(
        client=client,
        config=config,
        mode=mode,
        secrets=secrets,
        utils=utils,
    )

    # ── Execute ───────────────────────────────────────────────────────────────
    all_ops = []
    for i, step_config in enumerate(configs, 1):
        if len(configs) > 1:
            logger.info("── Step %d/%d ──", i, len(configs))
        ops = build_plan(step_config, mode=mode)
        all_ops.extend(ops)
    logger.info("Plan: %d operations total", len(all_ops))
    execute_all(all_ops, ctx)


def _load_target(targets_file: str, target_name: str, secrets: "SecretsProvider") -> dict:
    """Load auth credentials from a targets.yml file."""
    import yaml
    p = Path(targets_file)
    if not p.is_file():
        logging.getLogger("odoo_configurator").error("Targets file not found: %s", targets_file)
        sys.exit(1)
    with open(p) as f:
        targets_config = yaml.safe_load(f)
    targets = targets_config.get("targets", {})
    if target_name not in targets:
        logging.getLogger("odoo_configurator").error(
            "Target '%s' not found in %s. Available: %s",
            target_name, targets_file, list(targets.keys())
        )
        sys.exit(1)
    return _resolve_auth(targets[target_name], secrets)


def _resolve_auth(auth: dict, secrets: "SecretsProvider") -> dict:
    """Resolve env:// URIs in auth credentials."""
    return {k: secrets.resolve(v) for k, v in auth.items()}


if __name__ == "__main__":
    main()
