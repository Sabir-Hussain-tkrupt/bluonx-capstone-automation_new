"""US states (50 + DC) for the Projects / Vendors "State" filter.

`projects.state` and `vendors.state` are free text, so a row may hold either
the postal code ("MO") or the full name ("Missouri"). The filter accepts either
spelling and matches both, case-insensitively.
"""

from __future__ import annotations

US_STATES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
    "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}

_BY_NAME = {name.lower(): code for code, name in US_STATES.items()}


def resolve_state(value: str | None) -> tuple[str, str] | None:
    """(code, name) for a postal code or full name, or None if unknown."""
    if not value:
        return None
    cleaned = " ".join(value.split())
    code = cleaned.upper()
    if code in US_STATES:
        return code, US_STATES[code]
    code = _BY_NAME.get(cleaned.lower())
    return (code, US_STATES[code]) if code else None


def state_or_filter(value: str, column: str = "state") -> str | None:
    """PostgREST `or=(…)` expression matching the code or the full name.

    Uses `ilike` without wildcards = case-insensitive equality. Names are
    double-quoted so the space in "New York" survives. None if unknown.
    """
    resolved = resolve_state(value)
    if resolved is None:
        return None
    code, name = resolved
    return f'{column}.ilike.{code},{column}.ilike."{name}"'


def state_options(values) -> list[dict[str, str]]:
    """Filter options for the states that actually occur in `values`.

    A known state (code or full name, any case) becomes one option keyed by its
    code, so "MO" and "Missouri" collapse into "Missouri (MO)". Any other
    non-blank text is kept as typed, merged case-insensitively. Sorted by label.
    """
    options: dict[str, dict[str, str]] = {}
    for raw in values:
        if not isinstance(raw, str):
            continue
        cleaned = " ".join(raw.split())
        if not cleaned:
            continue
        resolved = resolve_state(cleaned)
        if resolved:
            code, name = resolved
            options.setdefault(code, {"value": code, "label": f"{name} ({code})"})
        else:
            options.setdefault(cleaned.lower(), {"value": cleaned, "label": cleaned})
    return sorted(options.values(), key=lambda o: o["label"].lower())
