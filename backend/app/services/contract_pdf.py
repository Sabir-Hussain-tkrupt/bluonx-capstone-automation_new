"""
Contract PDF generation.

Generates the firm standard-terms subcontract PDF from award data using
reportlab (pure-Python, no system deps). The legal terms body lives in an
ISOLATED, SWAPPABLE Jinja template (`templates/contracts/firm_terms.txt.j2`)
so the client's own boilerplate is a one-file swap; this module only lays that
text into a PDF and appends the signature block.

The signature block embeds the literal anchor strings `/vendor_sig/` and
`/owner_sig/` (rendered in white so they're invisible on the page) — DocuSign's
`SignHere` anchor tabs (built in docusign_client.build_envelope_definition) snap
onto these strings, so the PDF and the envelope stay in lock-step.
"""

from __future__ import annotations

import io
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from reportlab.lib.colors import white
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def _uncompressed_canvas(*args, **kwargs):
    """Canvas factory with page compression OFF, so the invisible anchor strings
    (`/vendor_sig/`, `/owner_sig/`) live as literal text in the PDF stream — which
    keeps DocuSign's anchor-tab matching robust and the output greppable/testable."""
    kwargs["pageCompression"] = 0
    return Canvas(*args, **kwargs)

# Anchor strings shared with the envelope builder. The contract PDF embeds these
# (invisibly); the SignHere tabs anchor onto them. Keep both sides in sync.
VENDOR_SIGN_ANCHOR = "/vendor_sig/"
OWNER_SIGN_ANCHOR = "/owner_sig/"

_TERMS_DIR = Path(__file__).resolve().parent.parent / "templates" / "contracts"
_TERMS_TEMPLATE = "firm_terms.txt.j2"

# Placeholder until the client supplies subcontract boilerplate (decision #2 /
# flagged in CURRENT_PHASE_TASKS.md). The plumbing is template-agnostic.
DEFAULT_PAYMENT_TERMS = (
    "Net 30 days from receipt of approved invoice. Progress payments billed "
    "monthly against completed work, subject to retainage as specified by the "
    "Contractor. [Placeholder — client subcontract terms pending.]"
)

_terms_env = Environment(
    loader=FileSystemLoader(str(_TERMS_DIR)),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


def _fmt_money(value: Any) -> str:
    if value in (None, ""):
        return "$0.00"
    try:
        return f"${Decimal(str(value)):,.2f}"
    except Exception:
        return str(value)


def _fmt_date(value: Any) -> str:
    if value in (None, ""):
        return "[to be determined]"
    if isinstance(value, (date, datetime)):
        return value.strftime("%B %d, %Y")
    s = str(value)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).strftime("%B %d, %Y")
    except ValueError:
        return s


def build_schedule_sentence(
    start_date: Any, end_date: Any, work_duration_days: Any
) -> str:
    """The SCHEDULE clause, in three shapes:
      - concrete window  → both a start and a duration resolve ("{start} to {end},
        a duration of {N} days")
      - relative         → a duration but no start ("{N} days of the effective date")
      - schedule-only    → no duration → omit the day count entirely

    Kept pure and separate so each case is directly unit-testable."""
    if work_duration_days and start_date and end_date:
        return (
            f"The Subcontractor shall commence work on or about {_fmt_date(start_date)} "
            f"and complete the work by {_fmt_date(end_date)}, a duration of "
            f"{work_duration_days} days, time being of the essence."
        )
    if work_duration_days:
        return (
            f"The Subcontractor shall complete the work within {work_duration_days} "
            "days of the effective date, time being of the essence."
        )
    if start_date:
        return (
            f"The Subcontractor shall commence work on or about {_fmt_date(start_date)} "
            "and complete the work in accordance with the agreed schedule, time being "
            "of the essence."
        )
    return (
        "The Subcontractor shall complete the work in accordance with the agreed "
        "schedule, time being of the essence."
    )


def render_terms_text(context: dict) -> str:
    """Render the swappable legal-terms body. Pure (no PDF) — easy to unit-test."""
    template = _terms_env.get_template(_TERMS_TEMPLATE)
    return template.render(
        vendor_company=context.get("vendor_company") or "Subcontractor",
        task_name=context.get("task_name") or "the contracted scope",
        project_name=context.get("project_name") or "the project",
        award_amount_formatted=_fmt_money(context.get("award_amount")),
        schedule_sentence=build_schedule_sentence(
            context.get("start_date"),
            context.get("end_date"),
            context.get("work_duration_days"),
        ),
        # Validity is rendered relatively at send-time; the concrete valid_until is
        # not known until signing. Defaults to the 1-year term.
        contract_valid_days=context.get("contract_valid_days") or 365,
        # Dormant seam — absent until the signed-SOW date task supplies it.
        sow_signed_date=context.get("sow_signed_date"),
        payment_terms=context.get("payment_terms") or DEFAULT_PAYMENT_TERMS,
    )


def build_contract_pdf(context: dict) -> bytes:
    """Render the contract PDF and return its bytes (starts with b"%PDF").

    `context` keys (all optional, defensively defaulted):
      contract_number, vendor_company, vendor_contact_name, owner_signer_name,
      award_amount, start_date, end_date, project_name, task_name, payment_terms,
      contract_valid_days, work_duration_days, sow_signed_date, and the firm
      contact block (firm_name, firm_contact_email, firm_contact_phone,
      firm_contact_address).
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        title=f"Subcontract {context.get('contract_number', '')}".strip(),
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
    )

    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    h1 = styles["Heading1"]
    meta = ParagraphStyle("meta", parent=body, fontSize=9, leading=12)
    sig_label = ParagraphStyle("siglabel", parent=body, fontSize=11, leading=14)
    # Truly-invisible anchor text: white, 1pt, 1pt leading — present in the PDF
    # stream for DocuSign's SignHere tab to find, but adds ~no height and is not
    # visible to a human reader. It sits ALONE in a whitespace band (below) so the
    # stamped signature lands in clean space, not on the printed name.
    anchor_style = ParagraphStyle(
        "anchor", parent=body, textColor=white, fontSize=1, leading=1
    )

    flow: list = []
    flow.append(Paragraph("SUBCONTRACT AGREEMENT", h1))
    flow.append(
        Paragraph(
            f"Contract No. {context.get('contract_number', '[pending]')}", meta
        )
    )
    flow.append(Spacer(1, 6))
    flow.append(
        Paragraph(
            f"Between {context.get('firm_name') or 'BluOnX Development LLC'} "
            f"(Contractor) and "
            f"{context.get('vendor_company', 'Subcontractor')} (Subcontractor).",
            meta,
        )
    )

    # Firm contact-information block. One Paragraph per set value so the
    # lines are not flattened; blanks are omitted so a partially-configured block
    # still renders cleanly.
    firm_lines = [
        context.get("firm_name"),
        context.get("firm_contact_address"),
        context.get("firm_contact_phone"),
        context.get("firm_contact_email"),
    ]
    firm_lines = [str(v) for v in firm_lines if v]
    if firm_lines:
        flow.append(Spacer(1, 8))
        flow.append(Paragraph("Contractor contact:", meta))
        for line in firm_lines:
            flow.append(Paragraph(line, meta))

    flow.append(Spacer(1, 14))

    # Legal terms body — rendered from the swappable template, one paragraph per
    # blank-line-separated block so reportlab wraps it cleanly.
    terms = render_terms_text(context)
    for block in terms.split("\n\n"):
        text = block.strip().replace("\n", " ")
        if not text:
            continue
        flow.append(Paragraph(text, body))
        flow.append(Spacer(1, 8))

    flow.append(Spacer(1, 24))
    flow.append(Paragraph("SIGNATURES", styles["Heading2"]))
    flow.append(Spacer(1, 10))

    vendor_name = context.get("vendor_contact_name") or context.get(
        "vendor_company"
    ) or "Subcontractor"
    owner_name = context.get("owner_signer_name") or "BluOnX Authorized Signer"

    # Each signature block: printed role+name label, then a tall WHITESPACE BAND,
    # then the invisible anchor alone at the bottom of that band, then the sign/date
    # line. The DocuSign signature stamps upward from the anchor into the empty band
    # — clear of the name above and the line below (the offsets in
    # docusign_client.build_envelope_definition keep it inside the band).
    def _signature_block(role: str, name: str, anchor: str) -> None:
        flow.append(Paragraph(f"{role}: {name}", sig_label))
        flow.append(Spacer(1, 56))  # whitespace band the signature lands in
        flow.append(Paragraph(anchor, anchor_style))  # invisible anchor, alone
        flow.append(Spacer(1, 8))
        flow.append(
            Paragraph("X _______________________________   Date: ____________", body)
        )
        flow.append(Spacer(1, 30))

    # Visual block order is independent of signing order; the DocuSign routing
    # (owner routingOrder 1, vendor 2) is set in contract_envelope_service.
    _signature_block("Contractor", owner_name, OWNER_SIGN_ANCHOR)  # signs first (routingOrder 1)
    _signature_block("Subcontractor", vendor_name, VENDOR_SIGN_ANCHOR)  # signs second (routingOrder 2)

    doc.build(flow, canvasmaker=_uncompressed_canvas)
    return buffer.getvalue()
