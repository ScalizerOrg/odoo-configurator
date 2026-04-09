# Copyright 2025 Scalizer (<https://www.scalizer.fr>)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

"""
Utils — path resolution and miscellaneous helpers.

The key improvement over the old Utils class:
  - Takes an explicit base_path instead of reading sys.argv[1] at call time.
  - No god-object reference — just a Path and a search order.
  - Raises FileNotFoundError with a clear message that names all searched paths.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class Utils:
    """
    Utility helpers, anchored to a base directory.

    base_path: root directory for relative file resolution (typically the
               directory containing the top-level YAML config file).
    """

    def __init__(self, base_path: Path | str | None = None) -> None:
        self.base_path = Path(base_path).resolve() if base_path else Path.cwd()

    def resolve_path(self, path: str) -> str:
        """
        Resolve a relative file path to an absolute path.

        Search order:
          1. As given (absolute or relative to cwd)
          2. Relative to base_path
          3. Relative to base_path / 'datas'

        Returns the absolute path as a string.
        Raises FileNotFoundError if not found in any location.
        """
        if not path:
            return ""
        p = Path(path)
        candidates = [
            p,
            self.base_path / p,
            self.base_path / "datas" / p,
        ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate.resolve())
        searched = "\n  ".join(str(c.resolve()) for c in candidates)
        raise FileNotFoundError(
            f"File not found: '{path}'\nSearched:\n  {searched}"
        )

    def resolve_dir(self, path: str) -> str:
        """
        Resolve a relative directory path to an absolute path.

        Same search order as resolve_path but checks for directories.
        """
        if not path:
            return ""
        p = Path(path)
        candidates = [
            p,
            self.base_path / p,
            self.base_path / "datas" / p,
        ]
        for candidate in candidates:
            if candidate.is_dir():
                return str(candidate.resolve())
        searched = "\n  ".join(str(c.resolve()) for c in candidates)
        raise NotADirectoryError(
            f"Directory not found: '{path}'\nSearched:\n  {searched}"
        )
