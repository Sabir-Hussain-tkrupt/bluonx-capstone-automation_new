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


# ── Row-backed fake (for paginated read paths) ─────────────────────────────
#
# The resolver-driven fake above answers "what did the router ask for"; this one
# answers "what would Postgres have returned". Seed rows per table (or view),
# and filters / ordering / range actually apply, so a test can assert that page
# 2 really is the second slice rather than trusting the router's arithmetic.


class _FakeRowsQuery:
    """Applies eq / is_ / in_ / order / range over seeded rows."""

    def __init__(self, rows: list[dict]):
        self._rows = list(rows)
        self._eq: list[tuple[str, str]] = []
        self._in: list[tuple[str, set]] = []
        self._is_null: list[str] = []
        self._order: list[tuple[str, bool]] = []
        self._range: tuple[int, int] | None = None
        self._limit: int | None = None
        self._single = False
        self._want_count = False

    def select(self, *_a, **kwargs) -> "_FakeRowsQuery":
        self._want_count = kwargs.get("count") == "exact"
        return self

    def eq(self, col, val) -> "_FakeRowsQuery":
        self._eq.append((col, str(val)))
        return self

    def in_(self, col, vals) -> "_FakeRowsQuery":
        self._in.append((col, {str(v) for v in vals}))
        return self

    def is_(self, col, val) -> "_FakeRowsQuery":
        if val == "null":
            self._is_null.append(col)
        return self

    def order(self, col, desc: bool = False, **_k) -> "_FakeRowsQuery":
        self._order.append((col, desc))
        return self

    def range(self, start: int, end: int) -> "_FakeRowsQuery":
        self._range = (start, end)
        return self

    def limit(self, n: int) -> "_FakeRowsQuery":
        self._limit = n
        return self

    def single(self) -> "_FakeRowsQuery":
        self._single = True
        return self

    def maybe_single(self) -> "_FakeRowsQuery":
        self._single = True
        return self

    def execute(self) -> FakeResponse:
        rows = self._rows
        for col, val in self._eq:
            rows = [r for r in rows if str(r.get(col)) == val]
        for col, vals in self._in:
            rows = [r for r in rows if str(r.get(col)) in vals]
        for col in self._is_null:
            rows = [r for r in rows if r.get(col) is None]

        # count is the filtered total, before range/limit — same as PostgREST,
        # which is why the service can ask for it with .limit(1).
        total = len(rows) if self._want_count else None

        # Applied last-key-first so the first .order() call is the primary sort.
        for col, desc in reversed(self._order):
            rows = sorted(rows, key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)

        if self._range is not None:
            start, end = self._range
            rows = rows[start : end + 1]
        elif self._limit is not None:
            rows = rows[: self._limit]

        if self._single:
            return FakeResponse(rows[0] if rows else None, total)
        return FakeResponse(rows, total)


class FakeRowsSupabase:
    """Supabase stand-in backed by seeded rows keyed by table (or view) name."""

    def __init__(self, tables: dict[str, list[dict]] | None = None):
        self.tables: dict[str, list[dict]] = tables if tables is not None else {}

    def table(self, name: str) -> _FakeRowsQuery:
        return _FakeRowsQuery(self.tables.get(name, []))
