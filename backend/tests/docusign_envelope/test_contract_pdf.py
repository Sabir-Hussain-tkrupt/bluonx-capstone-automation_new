"""Contract PDF generation (reportlab) — Task 9.3b / 9.5 document."""

from app.services.contract_pdf import (
    OWNER_SIGN_ANCHOR,
    VENDOR_SIGN_ANCHOR,
    build_contract_pdf,
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
