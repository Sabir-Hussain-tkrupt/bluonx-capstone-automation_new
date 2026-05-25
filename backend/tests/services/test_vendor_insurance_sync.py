"""Unit tests for recompute_vendor_insurance_expiration (Task 7.4.5).

Uses a small fake supabase double that records the exact filter chain the
service builds and resolves queries against an in-memory document list.
The service's contract:

  vendors.insurance_expiration_date = MAX(expiration_date)
    over vendor_documents WHERE vendor_id = :id
      AND document_type = 'insurance_certificate'
      AND status = 'valid'
      AND expiration_date IS NOT NULL
  -- or NULL when no such rows exist.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest

from app.services.vendor_service import recompute_vendor_insurance_expiration


# ── Fake supabase tailored to the service's chains ───────────────────────


class _Result:
    def __init__(self, data):
        self.data = data


class _NotIs:
    """Implements `.not_.is_(col, val)` on a query."""

    def __init__(self, query: "_Query"):
        self._query = query

    def is_(self, col, val):
        self._query._filters.append(("not_is", col, val))
        return self._query


class _Query:
    def __init__(self, fake: "FakeVendorDB", table: str):
        self._fake = fake
        self._table = table
        self._op = "select"
        self._payload = None
        self._filters: list[tuple] = []
        self._order: tuple | None = None
        self._limit: int | None = None

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    @property
    def not_(self) -> _NotIs:
        return _NotIs(self)

    def order(self, col, desc=False):
        self._order = (col, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        return self._fake._resolve(self)


def _matches(row, filters):
    for kind, col, val in filters:
        actual = row.get(col)
        if kind == "eq" and actual != val:
            return False
        if kind == "not_is":
            if val == "null" and actual is None:
                return False
    return True


class FakeVendorDB:
    """Records query chains so tests can assert on the exact filter set
    used. Resolves vendor_documents selects from an in-memory list and
    captures vendor updates."""

    def __init__(self, documents: list[dict] | None = None):
        self.documents: list[dict] = documents or []
        self.vendor_updates: list[tuple[str, dict]] = []
        self.queries: list[_Query] = []

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    @property
    def last_select_query(self) -> _Query | None:
        for q in reversed(self.queries):
            if q._table == "vendor_documents" and q._op == "select":
                return q
        return None

    def _resolve(self, q: _Query):
        self.queries.append(q)

        if q._table == "vendor_documents" and q._op == "select":
            rows = [r for r in self.documents if _matches(r, q._filters)]
            if q._order is not None:
                col, desc = q._order
                rows = sorted(rows, key=lambda r: r.get(col) or "", reverse=desc)
            if q._limit is not None:
                rows = rows[: q._limit]
            return _Result(rows)

        if q._table == "vendors" and q._op == "update":
            # Capture the vendor_id from the filter chain and the payload.
            vendor_id = None
            for kind, col, val in q._filters:
                if kind == "eq" and col == "id":
                    vendor_id = val
            self.vendor_updates.append((vendor_id, q._payload))
            return _Result([{"id": vendor_id, **q._payload}])

        return _Result([])


def _doc(
    *,
    vendor_id,
    document_type: str = "insurance_certificate",
    status: str = "valid",
    expiration_date: date | None = None,
) -> dict:
    return {
        "id": str(uuid4()),
        "vendor_id": str(vendor_id),
        "document_type": document_type,
        "status": status,
        "expiration_date": expiration_date.isoformat() if expiration_date else None,
    }


# ── Tests ────────────────────────────────────────────────────────────────


class TestRecomputeVendorInsuranceExpiration:
    def test_recompute_with_no_certs_sets_null(self):
        vendor_id = uuid4()
        db = FakeVendorDB(documents=[])

        result = recompute_vendor_insurance_expiration(db, vendor_id)

        assert result is None
        assert db.vendor_updates == [
            (str(vendor_id), {"insurance_expiration_date": None})
        ]

    def test_recompute_picks_max_across_multiple_certs(self):
        vendor_id = uuid4()
        today = date.today()
        max_date = today + timedelta(days=200)
        db = FakeVendorDB(
            documents=[
                _doc(vendor_id=vendor_id, expiration_date=today + timedelta(days=50)),
                _doc(vendor_id=vendor_id, expiration_date=max_date),
                _doc(vendor_id=vendor_id, expiration_date=today + timedelta(days=100)),
            ]
        )

        result = recompute_vendor_insurance_expiration(db, vendor_id)

        assert result == max_date
        assert db.vendor_updates == [
            (str(vendor_id), {"insurance_expiration_date": max_date.isoformat()})
        ]

    def test_recompute_ignores_expired_status_certs(self):
        """An `expired` row with a further-future date must not win."""
        vendor_id = uuid4()
        today = date.today()
        valid_date = today + timedelta(days=30)
        db = FakeVendorDB(
            documents=[
                _doc(
                    vendor_id=vendor_id,
                    status="expired",
                    expiration_date=today + timedelta(days=365),
                ),
                _doc(vendor_id=vendor_id, status="valid", expiration_date=valid_date),
            ]
        )

        result = recompute_vendor_insurance_expiration(db, vendor_id)

        assert result == valid_date
        # And the query must explicitly filter on status='valid'.
        assert db.last_select_query is not None
        assert ("eq", "status", "valid") in db.last_select_query._filters

    def test_recompute_ignores_other_document_types(self):
        """A w9 with an expiration_date must not influence the result."""
        vendor_id = uuid4()
        today = date.today()
        cert_date = today + timedelta(days=100)
        db = FakeVendorDB(
            documents=[
                _doc(
                    vendor_id=vendor_id,
                    document_type="w9",
                    expiration_date=today + timedelta(days=999),
                ),
                _doc(vendor_id=vendor_id, expiration_date=cert_date),
            ]
        )

        result = recompute_vendor_insurance_expiration(db, vendor_id)

        assert result == cert_date
        # And the query must filter document_type='insurance_certificate'.
        assert db.last_select_query is not None
        assert (
            "eq",
            "document_type",
            "insurance_certificate",
        ) in db.last_select_query._filters

    def test_recompute_returns_the_set_value(self):
        vendor_id = uuid4()
        today = date.today()
        expiry = today + timedelta(days=75)
        db = FakeVendorDB(
            documents=[_doc(vendor_id=vendor_id, expiration_date=expiry)]
        )

        result = recompute_vendor_insurance_expiration(db, vendor_id)

        assert result == expiry
        # And whatever was returned is what was persisted.
        assert db.vendor_updates[0][1]["insurance_expiration_date"] == expiry.isoformat()
