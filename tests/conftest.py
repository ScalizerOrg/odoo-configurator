# conftest.py — shared fixtures and import stubs for the test suite.
#
# s6r_odoo imports xlrd at module level (via file_import.py), which is not
# installed in the test environment. We stub the entire s6r_odoo package in
# sys.modules before any test module imports it, so tests that don't need a
# real Odoo connection can run without xlrd or a live server.

import sys
from unittest.mock import MagicMock

# Build a minimal stub that satisfies all imports in client.py and evaluator.py
_s6r_stub = MagicMock()
_s6r_stub.OdooConnection = MagicMock

sys.modules.setdefault("s6r_odoo", _s6r_stub)
sys.modules.setdefault("xlrd", MagicMock())
