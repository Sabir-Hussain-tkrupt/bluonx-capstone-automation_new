"""Fixtures for the notes / subtrades / state-filter tests (migration 20261117).

Reuses the financial-module MemDB client: `fin_client(db, user)`.
"""

from tests.financial.conftest import ADMIN, PM, fin_client, identity  # noqa: F401
