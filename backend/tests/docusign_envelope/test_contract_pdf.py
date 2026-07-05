"""Contract PDF generation (reportlab) — Task 9.3b / 9.5 document."""

from app.services.contract_pdf import (
    OWNER_SIGN_ANCHOR,
    VENDOR_SIGN_ANCHOR,
    build_contract_pdf,
    build_schedule_sentence,
    render_terms_text,
)

CTX = {
    "contract_number": "CON-2026-ABCD1234",
    "vendor_company": "Acme Grading LLC",
    "vendor_contact_name": "Jane Doe",
    "award_amount": "145000.00",
    "start_date": "2026-07-01",
    "end_date": "2026-12-31",
    "project_name": "Maple Subdivision",
    "task_name": "Mass Grading",
}


def test_build_contract_pdf_returns_pdf_bytes():
    pdf = build_contract_pdf(CTX)
    assert isinstance(pdf, bytes)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1000


def test_pdf_embeds_both_signature_anchors():
    # The anchor strings must be present in the PDF stream so DocuSign's
    # SignHere anchor tabs can find them.
    pdf = build_contract_pdf(CTX)
    assert VENDOR_SIGN_ANCHOR.encode() in pdf
    assert OWNER_SIGN_ANCHOR.encode() in pdf


def test_terms_text_populates_award_data():
    terms = render_terms_text(CTX)
    assert "Acme Grading LLC" in terms
    assert "Mass Grading" in terms
    assert "$145,000.00" in terms
    # payment_terms placeholder fills when none supplied.
    assert "Net 30" in terms or "Placeholder" in terms


# ── contract-term rendering (Task 9.8) ───────────────────────────────────


def test_schedule_sentence_concrete_window():
    """Both start and duration resolve → a dated window with the day count."""
    s = build_schedule_sentence("2026-07-01", "2026-07-22", 21)
    assert "July 01, 2026" in s and "July 22, 2026" in s
    assert "a duration of 21 days" in s


def test_schedule_sentence_relative_when_start_null():
    """Start missing → relative phrasing off the effective date, no crash."""
    s = build_schedule_sentence(None, None, 21)
    assert "within 21 days of the effective date" in s


def test_schedule_sentence_omitted_when_duration_null():
    """Duration missing → no day count at all (neither concrete nor relative)."""
    s = build_schedule_sentence("2026-07-01", None, None)
    assert "days" not in s
    assert "agreed schedule" in s


def test_terms_text_renders_relative_validity():
    """Validity is relative at send-time (concrete valid_until unknown until signing)."""
    terms = render_terms_text({**CTX, "contract_valid_days": 730})
    assert "valid for 730 days from the effective date" in terms


def test_terms_text_renders_schedule_from_context():
    terms = render_terms_text({**CTX, "work_duration_days": 21})
    assert "a duration of 21 days" in terms


def test_sow_date_line_absent_by_default():
    """Dormant seam: no signed-SOW date yet → the line stays absent."""
    terms = render_terms_text(CTX)
    assert "Date of signed scope of work" not in terms


def test_sow_date_line_present_when_set():
    terms = render_terms_text({**CTX, "sow_signed_date": "2026-07-01"})
    assert "Date of signed scope of work: 2026-07-01" in terms


def test_pdf_renders_firm_contact_block():
    """The BluOnX contact block renders the configured firm-contact values."""
    pdf = build_contract_pdf(
        {**CTX, "firm_name": "BluOnX Development LLC",
         "firm_contact_email": "contracts@bluonx.example"}
    )
    assert b"contracts@bluonx.example" in pdf
