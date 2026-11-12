"""In-memory Supabase stand-in for the financial-module tests.

Seed rows per table; `.eq / .neq / .is_ / .in_` filter them, writes mutate them,
and `.rpc(name, params)` is recorded and answered by a per-test handler. That is
enough for the service and router code, which only ever chains these calls.

    db = MemDB({"budget_lines": [...]}, rpc={"fn_x": lambda params: [...]})
    db.rpc_calls  -> [("fn_x", {...}), ...]
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from postgrest.exceptions import APIError


class _Resp:
    def __init__(self, data: Any = None, count: int | None = None):
        self.data = data
        self.count = count


def api_error(code: str, message: str) -> APIError:
    """Build the APIError PostgREST raises for a SQLSTATE."""
    return APIError({"code": code, "message": message, "details": None, "hint": None})


class _Query:
    def __init__(self, db: MemDB, table: str):
        self._db = db
        self._table = table
        self._op = "select"
        self._payload: Any = None
        self._filters: list[tuple[str, str, Any]] = []
        self._single: str | None = None
        self._order: list[tuple[str, bool]] = []
        self._limit: int | None = None

    # operations
    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def insert(self, payload, *_a, **_k):
        self._op, self._payload = "insert", payload
        return self

    def update(self, payload, *_a, **_k):
        self._op, self._payload = "update", payload
        return self

    def delete(self, *_a, **_k):
        self._op = "delete"
        return self

    # filters / modifiers
    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def neq(self, col, val):
        self._filters.append(("neq", col, val))
        return self

    def is_(self, col, val):
        self._filters.append(("is", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, [str(v) for v in vals]))
        return self

    def order(self, col, desc: bool = False, **_k):
        self._order.append((col, desc))
        return self

    def limit(self, n, *_a, **_k):
        self._limit = n
        return self

    def range(self, *_a, **_k):
        return self

    def single(self):
        self._single = "strict"
        return self

    def maybe_single(self):
        self._single = "maybe"
        return self

    def _match(self, row: dict) -> bool:
        for kind, col, val in self._filters:
            cell = row.get(col)
            if kind == "eq" and str(cell) != str(val):
                return False
            if kind == "neq" and str(cell) == str(val):
                return False
            if kind == "in" and str(cell) not in val:
                return False
            if kind == "is":
                if val in ("null", None):
                    if cell is not None:
                        return False
                elif str(cell).lower() != str(val).lower():
                    return False
        return True

    def execute(self):
        err = self._db.errors.get((self._table, self._op))
        if err is not None:
            raise err
        rows = self._db.tables.setdefault(self._table, [])
        if self._op == "select":
            out = [copy.deepcopy(r) for r in rows if self._match(r)]
            for col, desc in reversed(self._order):
                out.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
            if self._limit is not None:
                out = out[: self._limit]
            if self._single:
                if not out:
                    if self._single == "maybe":
                        return None
                    raise api_error("PGRST116", "no rows")
                return _Resp(out[0])
            return _Resp(out, count=len(out))
        if self._op == "insert":
            payloads = self._payload if isinstance(self._payload, list) else [self._payload]
            created = []
            for p in payloads:
                row = {"id": str(uuid4()), **copy.deepcopy(p)}
                rows.append(row)
                created.append(copy.deepcopy(row))
            return _Resp(created)
        if self._op == "update":
            hit = [r for r in rows if self._match(r)]
            for r in hit:
                r.update(copy.deepcopy(self._payload))
            return _Resp([copy.deepcopy(r) for r in hit])
        if self._op == "delete":
            hit = [r for r in rows if self._match(r)]
            rows[:] = [r for r in rows if not self._match(r)]
            return _Resp([copy.deepcopy(r) for r in hit])
        return _Resp([])


class _Rpc:
    def __init__(self, db: MemDB, name: str, params: dict):
        self._db, self._name, self._params = db, name, params

    def execute(self):
        self._db.rpc_calls.append((self._name, copy.deepcopy(self._params)))
        handler = self._db.rpc_handlers.get(self._name)
        if handler is None:
            return _Resp([])
        result = handler(self._params)
        if isinstance(result, Exception):
            raise result
        return _Resp(result)


class _Bucket:
    def __init__(self, db: MemDB, bucket: str):
        self._db, self._bucket = db, bucket

    def upload(self, path, data, file_options=None):
        self._db.uploads.append((self._bucket, path, len(data)))
        return {"path": path}

    def remove(self, paths):
        self._db.removed.extend((self._bucket, p) for p in paths)
        return []

    def create_signed_url(self, path, expires_in):
        return {"signedURL": f"https://signed.example/{self._bucket}/{path}?e={expires_in}"}


class _Storage:
    def __init__(self, db: MemDB):
        self._db = db

    def from_(self, bucket: str):
        return _Bucket(self._db, bucket)


class MemDB:
    def __init__(
        self,
        tables: dict[str, list[dict]] | None = None,
        rpc: dict[str, Callable[[dict], Any]] | None = None,
    ):
        self.tables: dict[str, list[dict]] = copy.deepcopy(tables or {})
        self.rpc_handlers = rpc or {}
        self.rpc_calls: list[tuple[str, dict]] = []
        self.errors: dict[tuple[str, str], Exception] = {}
        self.uploads: list[tuple[str, str, int]] = []
        self.removed: list[tuple[str, str]] = []
        self.storage = _Storage(self)

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def rpc(self, name: str, params: dict | None = None) -> _Rpc:
        return _Rpc(self, name, params or {})

    def calls(self, name: str) -> list[dict]:
        return [p for n, p in self.rpc_calls if n == name]
