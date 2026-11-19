"""Trade "family" lookups for subtrade-aware matching.

Trades have one level of subtrades (migration 20261117). When matching vendors
to a trade, the family is:

* the trade itself;
* its parent, when it is a subtrade (vendors registered for the whole trade,
  e.g. "Electrical", still fit an "Electrical › Commercial" task);
* its subtrades, when it has any (an older task on "Electrical" fits vendors
  registered for any Electrical subtrade).

Every lookup is best-effort: on any database hiccup the family degrades to the
trade alone, which is the pre-subtrade behaviour.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _rows(data: Any) -> list[dict]:
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def trade_family_ids(
    db,
    trade_id: str,
    parent_trade_id: str | None = None,
    *,
    include_parent: bool = True,
) -> list[str]:
    """Ids of the trade, its parent (if any) and its subtrades (if any).

    `parent_trade_id` may be passed when the caller already loaded the trade.
    `include_parent=False` gives the trade plus its subtrades only, which is
    what list FILTERS want ("Electrical" shows every Electrical subtrade, but
    "Electrical › Commercial" shows only Commercial). The trade's own id is
    always first.
    """
    trade_id = str(trade_id)
    family: list[str] = [trade_id]

    try:
        if parent_trade_id is None and include_parent:
            resp = (
                db.table("trades")
                .select("id, parent_trade_id")
                .eq("id", trade_id)
                .maybe_single()
                .execute()
            )
            row = _rows(resp.data if resp else None)
            parent_trade_id = row[0].get("parent_trade_id") if row else None

        if parent_trade_id:
            if include_parent:
                family.append(str(parent_trade_id))
        else:
            children = (
                db.table("trades")
                .select("id, parent_trade_id")
                .eq("parent_trade_id", trade_id)
                .execute()
            )
            for child in _rows(children.data if children else None):
                # Only real children count: guard against a row that is the
                # trade itself or that names a different parent.
                child_id = child.get("id")
                if child_id and str(child_id) != trade_id and str(child.get("parent_trade_id")) == trade_id:
                    family.append(str(child_id))
    except Exception:  # noqa: BLE001 - matching must never fail on this lookup
        logger.warning("Could not expand trade family for %s", trade_id, exc_info=True)
        return [trade_id]

    seen: set[str] = set()
    return [t for t in family if not (t in seen or seen.add(t))]
