"""Helpers for building safe PostgREST filter values."""

from app.core.us_states import state_or_filter


def escape_like_pattern(value: str) -> str:
    """Escape LIKE/ILIKE wildcards so user input is matched literally.

    Postgres treats % and _ as wildcards inside a LIKE/ILIKE pattern, with
    backslash as the default escape character. Interpolating raw search input
    into a pattern therefore lets a user type "%" to match every row, or "_"
    to match any single character.

    "*" is escaped too: PostgREST accepts it as an alias for % in the like and
    ilike operators, so an unescaped "*" is also a match-everything wildcard.
    Verified against the live API — "Acm*" returns exactly what "Acm%" returns.

    The backslash is escaped first so the subsequent replacements don't
    double-escape the escape character itself.

    Callers still wrap the result in their own % delimiters:

        q.ilike("name", f"%{escape_like_pattern(search)}%")
    """
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
        .replace("*", "\\*")
    )


def apply_state_filter(query, value: str):
    """Filter a projects / vendors query by US state.

    A known state (code or full name) matches rows holding either spelling,
    case-insensitively. Anything else is matched literally (case-insensitive).
    """
    expr = state_or_filter(value)
    if expr is not None:
        return query.or_(expr)
    return query.ilike("state", escape_like_pattern(" ".join(value.split())))


def fetch_column_values(query_factory, column: str, batch: int = 1000) -> list:
    """Every value of `column` for the rows a query matches.

    `query_factory()` must return a fresh filtered query selecting `column`.
    Reads in batches so PostgREST's 1000-row cap never truncates the result.
    """
    values: list = []
    start = 0
    while True:
        rows = (
            query_factory()
            .order("id")
            .range(start, start + batch - 1)
            .execute()
            .data
            or []
        )
        values.extend(row.get(column) for row in rows)
        if len(rows) < batch:
            return values
        start += batch
