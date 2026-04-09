# Copyright 2025 Scalizer (<https://www.scalizer.fr>)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

"""
Secrets resolution — maps credential URI schemes to their values.

Supported schemes in v4:
  literal          → returned as-is          (e.g. "admin")
  env://VAR_NAME   → os.environ[VAR_NAME]    (also loads from .env file)

Reserved for future implementation (raise NotImplementedError with instructions):
  bw://Collection/Item     → Bitwarden via BW_SESSION
  keyring://service/key    → OS keychain via `keyring` library

.env file:
  Automatically loaded from the current working directory upward.
  Values in .env are available via env:// and os.environ.
  The .env file must be gitignored — never committed.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env once when the module is imported.
# find_dotenv() searches cwd upward; dotenv_path=None means auto-discover.
load_dotenv(override=False)  # env vars already set in the shell take precedence


class SecretsProvider:
    """
    Resolves credential values from various sources based on URI scheme.

    Usage:
        secrets = SecretsProvider()
        password = secrets.resolve("env://ODOO_PROD_PASSWORD")
        password = secrets.resolve("admin")          # literal
    """

    def resolve(self, value: object) -> object:
        """
        Resolve a credential value.

        Non-string values are returned unchanged.
        Strings without a recognised scheme are returned as literals.
        """
        if not isinstance(value, str):
            return value

        if value.startswith("env://"):
            return self._from_env(value[len("env://"):])

        if value.startswith("bw://"):
            raise NotImplementedError(
                "Bitwarden secrets (bw://) are not yet supported in v4.0.\n"
                "Use 'env://VAR_NAME' with a .env file instead.\n"
                "Bitwarden support is planned for a future release."
            )

        if value.startswith("keyring://"):
            raise NotImplementedError(
                "OS keychain secrets (keyring://) are not yet supported in v4.0.\n"
                "Use 'env://VAR_NAME' with a .env file instead.\n"
                "Keyring support is planned for a future release."
            )

        return value  # literal

    def get_env_var(self, var_name: str) -> str:
        """
        Retrieve an environment variable by name.

        LEGACY: this method exists so that 'get_env_var(\"NAME\")' expressions
        in YAML files continue to work. Prefer the 'env://NAME' URI scheme
        in new configurations.
        """
        # LEGACY: get_env_var() — use env://VAR_NAME in new configs
        return self._from_env(var_name)

    # ── Private ───────────────────────────────────────────────────────────────

    def _from_env(self, var_name: str) -> str:
        value = os.environ.get(var_name)
        if value is None:
            raise RuntimeError(
                f"Environment variable '{var_name}' is not set.\n"
                f"Add it to your .env file:\n"
                f"  echo '{var_name}=your_value' >> .env\n"
                f"Or export it in your shell:\n"
                f"  export {var_name}=your_value"
            )
        return value
