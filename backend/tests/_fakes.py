"""Lightweight fakes for router unit tests that mock the Supabase client.

The project-wide convention (see e.g. tests/bid_package_creation/conftest.py)
is to override `get_supabase` with a mock rather than round-trip a live DB.
These helpers give the vendor / project / geocoding endpoint tests the same
isolation: no real Supabase instance, no auth sign-in, no leftover rows.

`FakeSupabase` is driven by a `resolver(table, op, payload) -> FakeResponse`
callback, so a test decides what each `db.table(...).<op>().execute()` returns
based on which table and operation the router reached.
"""

from __future__ import annotations

from typing import Any, Callable

Resolver = Callable[[str, str, Any], "FakeResponse"]


class FakeResponse:
    """Mimics a postgrest APIResponse — carries `.data` and `.count`."""

    def __init__(self, data: Any = None, count: int | None = None):
        self.data = data
        self.count = count


class _FakeQuery:
    """Records a table operation and defers the result to the resolver.

    Every filter / modifier (`eq`, `is_`, `ilike`, `single`, ...) is a
    chainable no-op; only the operation kind (select/insert/update/delete)
    and any write payload are captured, then handed to the resolver on
    `execute()`.
    """

    def __init__(self, table: str, resolver: Resolver):
        self._table = table
        self._resolver = resolver
        self._op = "select"
        self._payload: Any = None

    def select(self, *a, **k) -> "_FakeQuery":
        self._op = "select"
        return self

    def insert(self, payload=None, *a, **k) -> "_FakeQuery":
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload=None, *a, **k) -> "_FakeQuery":
        self._op = "update"
        self._payload = payload
        return self

    def delete(self, *a, **k) -> "_FakeQuery":
        self._op = "delete"
        return self

    # ── chainable filters / modifiers (no-ops) ──────────────────────────
    def eq(self, *a, **k) -> "_FakeQuery":
        return self

    def neq(self, *a, **k) -> "_FakeQuery":
        return self

    def is_(self, *a, **k) -> "_FakeQuery":
        return self

    def ilike(self, *a, **k) -> "_FakeQuery":
        return self

    def like(self, *a, **k) -> "_FakeQuery":
        return self

    def in_(self, *a, **k) -> "_FakeQuery":
        return self

    def order(self, *a, **k) -> "_FakeQuery":
        return self

    def range(self, *a, **k) -> "_FakeQuery":
        return self

    def limit(self, *a, **k) -> "_FakeQuery":
        return self

    def single(self, *a, **k) -> "_FakeQuery":
        return self

    def maybe_single(self, *a, **k) -> "_FakeQuery":
        return self

    @property
    def not_(self) -> "_FakeQuery":
        return self

    def execute(self) -> "FakeResponse":
        return self._resolver(self._table, self._op, self._payload)


class FakeSupabase:
    """Stand-in for the Supabase client, driven by a resolver callback."""

    def __init__(self, resolver: Resolver):
        self._resolver = resolver

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(name, self._resolver)
