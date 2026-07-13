"""
Dev-only preview: render the 5 Phase 10.4 milestone email templates (HTML + txt)
with realistic sample context into backend/tmp_rendered/ so they can be eyeballed
in a browser. No sending, no scheduler, no DB.

Run:
    backend/.venv/Scripts/python.exe backend/scripts/preview_milestone_emails.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.services.template_renderer import template_renderer  # noqa: E402

_OUT_DIR = _BACKEND_DIR / "tmp_rendered"

# Shared sample values.
_PROJECT = "Phoenix Logistics Park - Building C"
_TASK = "Site Grading & Earthwork"
_MILESTONE = "Rough Grading Complete"
_PORTAL_URL = "http://localhost:5173/milestone/raw-token-abc123"
_MILESTONE_URL = (
    "http://localhost:5173/projects/11111111-1111-1111-1111-111111111111"
    "/tasks/22222222-2222-2222-2222-222222222222"
    "/milestones/33333333-3333-3333-3333-333333333333"
)

_VENDOR_CTX = {
    "vendor_contact_name": "Marcus Delgado",
    "company_name": "Summit Earthworks LLC",
    "project_name": _PROJECT,
    "task_name": _TASK,
    "milestone_name": _MILESTONE,
    "start_date_formatted": "September 15, 2026",
    "end_date_formatted": "October 03, 2026",
    "portal_url": _PORTAL_URL,
}

_PM_BASE_CTX = {
    "recipient_full_name": "Dana Whitfield",
    "project_name": _PROJECT,
    "task_name": _TASK,
    "milestone_name": _MILESTONE,
    "vendor_company_name": "Summit Earthworks LLC",
    "vendor_contact_name": "Marcus Delgado",
    "vendor_contact_email": "marcus@summitearthworks.example",
    "vendor_contact_phone": "(602) 555-0148",
    "end_date_formatted": "October 03, 2026",
    "milestone_url": _MILESTONE_URL,
}

# stem -> context dict
_PREVIEWS: dict[str, dict] = {
    "milestone_start_check": _VENDOR_CTX,
    "milestone_progress_check": _VENDOR_CTX,
    "milestone_completion_check": _VENDOR_CTX,
    "milestone_delay_alert": _PM_BASE_CTX,
    "milestone_no_response_alert": {
        **_PM_BASE_CTX,
        "check_type_label": "start confirmation",
        "days_silent": 4,
    },
}


def main() -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for stem, ctx in _PREVIEWS.items():
        html = template_renderer.render(f"{stem}.html", ctx)
        txt = template_renderer.render_text(f"{stem}.txt", ctx)
        html_path = _OUT_DIR / f"{stem}.html"
        txt_path = _OUT_DIR / f"{stem}.txt"
        html_path.write_text(html, encoding="utf-8")
        txt_path.write_text(txt, encoding="utf-8")
        written.append(html_path.name)
        written.append(txt_path.name)

    print(f"Rendered {len(written)} files into {_OUT_DIR}:")
    for name in written:
        print(f"  - {name}")


if __name__ == "__main__":
    main()
