"""Helpers for building safe PostgREST filter values."""


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
