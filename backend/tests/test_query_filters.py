"""Unit tests for LIKE/ILIKE pattern escaping.

These matter because search terms are interpolated straight into an ilike
pattern in every list endpoint (vendors, projects, tasks, bid templates). An
unescaped "%" there matches every row.
"""

from app.core.query_filters import escape_like_pattern


def test_plain_text_is_unchanged():
    assert escape_like_pattern("Acme Paving") == "Acme Paving"


def test_percent_is_escaped():
    assert escape_like_pattern("50%") == "50\\%"


def test_underscore_is_escaped():
    assert escape_like_pattern("a_b") == "a\\_b"


def test_backslash_is_escaped_first():
    # The backslash must be doubled before % and _ gain their own backslashes,
    # otherwise those escapes get broken by the backslash rule running later.
    assert escape_like_pattern("a\\b") == "a\\\\b"
    assert escape_like_pattern("\\%") == "\\\\\\%"


def test_combined_wildcards():
    assert escape_like_pattern("%_%") == "\\%\\_\\%"


def test_empty_string():
    assert escape_like_pattern("") == ""


def test_quotes_and_punctuation_pass_through():
    # Not LIKE metacharacters — these must not be mangled, they just need to
    # survive to Postgres as literals.
    assert escape_like_pattern("O'Brien & Sons (Ltd.), Inc.") == "O'Brien & Sons (Ltd.), Inc."
