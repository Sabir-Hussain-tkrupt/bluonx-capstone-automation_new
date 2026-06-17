"""
Manual "close bidding early" service path (open -> evaluating).

close_bidding is the PM action; it must move an OPEN package to 'evaluating'
(before or after deadline) and reject any non-open package with 409. No token
revocation, no invitation expiry (the deadline sweep owns that).
"""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services.invitation_tracking_service import (
    InvitationTrackingError,
    close_bidding,
)

PKG = str(uuid4())


def _make_db(package: dict, captured: list) -> MagicMock:
    """Mock supabase client: bid_packages select->single->execute returns
    `package`; update payloads are captured."""
    client = MagicMock()

    def _table(name):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.single.return_value = chain
        chain.limit.return_value = chain

        def _update(payload):
            captured.append({"table": name, "payload": payload})
            return chain

        chain.update.side_effect = _update

        def _execute():
            res = MagicMock()
            res.data = package if name == "bid_packages" else []
            return res

        chain.execute.side_effect = _execute
        return chain

    client.table.side_effect = _table
    return client


async def test_close_open_moves_to_evaluating():
    captured: list = []
    db = _make_db({"id": PKG, "status": "open"}, captured)
    result = await close_bidding(bid_package_id=PKG, db=db)
    assert result == {"id": PKG, "status": "evaluating"}
    pkg_updates = [c["payload"] for c in captured if c["table"] == "bid_packages"]
    assert pkg_updates and pkg_updates[0]["status"] == "evaluating"


@pytest.mark.parametrize("status", ["evaluating", "closed", "cancelled"])
async def test_close_rejects_non_open_409(status):
    captured: list = []
    db = _make_db({"id": PKG, "status": status}, captured)
    with pytest.raises(InvitationTrackingError) as ei:
        await close_bidding(bid_package_id=PKG, db=db)
    assert ei.value.status_code == 409
    # No write happened — the guard fired before the update.
    assert captured == []
