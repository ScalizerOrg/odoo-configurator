# Copyright 2025 Scalizer (<https://www.scalizer.fr>)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

"""
OdooClient — the single interface between odoo-configurator and Odoo.

Wraps s6r_odoo.OdooConnection. The `odoo` attribute gives direct access to
the s6r_odoo instance for scripts that need advanced ORM features.

Added on top of s6r_odoo:
  - get_image_url()   download a remote image and return it base64-encoded (cached)
  - get_image_local() read a local image file and return it base64-encoded
"""

from __future__ import annotations

import base64
import logging
import os
import pickle
from pathlib import Path
from typing import Any

import requests
from s6r_odoo import OdooConnection as _S6rOdoo

logger = logging.getLogger(__name__)

_IMAGE_CACHE_PATH = Path("/tmp/.configurator_image_cache")  # noqa: S108


class OdooClient:
    """
    Thin wrapper around s6r_odoo.OdooConnection.

    Instantiate once per target environment; pass it into Context.
    All get_* methods declared here are automatically available as
    YAML expressions via the evaluator namespace.
    """

    def __init__(
        self,
        url: str,
        db: str,
        user: str,
        password: str,
        version: float = 17.0,
        http_user: str | None = None,
        http_password: str | None = None,
        lang: str = "fr_FR",
        debug_xmlrpc: bool = False,
    ) -> None:
        self.odoo: _S6rOdoo = _S6rOdoo(
            url=url,
            dbname=db,
            user=user,
            password=password,
            version=version,
            http_user=http_user,
            http_password=http_password,
            debug_xmlrpc=debug_xmlrpc,
            lang=lang,
        )
        self._image_cache: dict[str, str] = self._load_image_cache()

    # ── Delegated methods (listed explicitly for IDE discoverability) ─────────

    @property
    def context(self) -> dict:
        return self.odoo.context

    def get_ref(self, xml_id: str) -> int:
        """Return the database id for an xml_id (e.g. 'base.EUR')."""
        return self.odoo.get_ref(xml_id)

    def get_record(self, model: str, rec_id: int, context: dict | None = None) -> dict:
        """Return a single record dict by id."""
        return self.odoo.get_record(model, rec_id, context=context)

    def get_search_id(self, model: str, domain: list, order: str = "id asc") -> int | None:
        """Return the first matching record id or None."""
        results = self.odoo.search_ids(model, domain, order=order, limit=1)
        return results[0] if results else None

    def get_country(self, code: str) -> int:
        """Return the id of a res.country by its 2-letter code."""
        return self.odoo.get_country(code)

    def get_menu(self, website_id: int, url: str) -> int:
        """Return the id of a website.menu by website_id and url."""
        return self.odoo.get_menu(website_id, url)

    def get_local_file(self, path: str, encode: bool = False) -> str:
        """Read a local file, optionally base64-encoding it."""
        return self.odoo.get_local_file(path, encode=encode)

    def get_xml_id_from_id(self, model: str, res_id: int) -> str | None:
        """Return the xml_id for a (model, res_id) pair, or None."""
        return self.odoo.get_xml_id_from_id(model, res_id)

    def get_id_from_xml_id(self, xml_id: str, no_raise: bool = False) -> int | None:
        """Return the database id for an xml_id, or None if not found."""
        return self.odoo.get_id_from_xml_id(xml_id, no_raise=no_raise)

    def default_get(self, model: str, field: str) -> Any:
        """Return the default value for a model field."""
        return self.odoo.default_get(model, field)

    def create_xml_id(self, module: str, model: str, name: str, res_id: int) -> None:
        """Create an ir.model.data entry linking xml_id → res_id."""
        import re
        safe_name = re.sub(r"[^a-zA-Z0-9]", "_", name).lower()
        self.odoo.create("ir.model.data", {
            "module": module,
            "name": safe_name,
            "model": model,
            "res_id": res_id,
        })

    # ── Image helpers ─────────────────────────────────────────────────────────

    def get_image_url(self, url: str) -> str:
        """
        Download an image from a URL and return it base64-encoded.
        Results are cached locally at /tmp/.configurator_image_cache
        to avoid re-downloading on repeated runs.
        """
        if url in self._image_cache:
            logger.debug("Image cache hit: %s", url)
            return self._image_cache[url]

        logger.debug("Downloading image: %s", url)
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        encoded = base64.b64encode(response.content).decode("utf-8", "ignore")
        self._image_cache[url] = encoded
        self._save_image_cache()
        return encoded

    def get_image_local(self, path: str) -> str:
        """Read a local image file and return it base64-encoded."""
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8", "ignore")

    # ── Image cache helpers ───────────────────────────────────────────────────

    def _load_image_cache(self) -> dict[str, str]:
        if _IMAGE_CACHE_PATH.is_file():
            try:
                with open(_IMAGE_CACHE_PATH, "rb") as f:
                    return pickle.load(f)  # noqa: S301
            except Exception:
                logger.debug("Could not load image cache — starting fresh.")
        return {}

    def _save_image_cache(self) -> None:
        try:
            with open(_IMAGE_CACHE_PATH, "wb") as f:
                pickle.dump(self._image_cache, f)
        except Exception as e:
            logger.debug("Could not save image cache: %s", e)
