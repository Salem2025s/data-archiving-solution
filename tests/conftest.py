"""Test bootstrap.

Sets dummy secrets so ``get_settings()`` never fails on import-time validation
during tests (the pure-logic tests do not connect to anything). Real values come
from ``.env`` in normal runs.
"""

import os

os.environ.setdefault("ORACLE_PASSWORD", "test-dummy")
os.environ.setdefault("POSTGRES_PASSWORD", "test-dummy")
