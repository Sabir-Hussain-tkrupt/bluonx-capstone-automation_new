"""
Tests for Jinja2 email template rendering.

Verifies that all email templates (bid invitation + 3 reminders, HTML and TXT)
render correctly with complete and partial context variables.
"""

import pytest
from jinja2 import TemplateNotFound

from app.services.template_renderer import template_renderer


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def invitation_context() -> dict:
    """Full context for bid invitation templates."""
    return {
        "vendor_contact_name": "John Smith",
        "vendor_company_name": "Smith Grading LLC",
        "project_name": "Sunset Ridge Phase 2",
        "project_location": "Austin, TX",
        "project_description": "A 120-lot residential subdivision with full horizontal infrastructure including roads, utilities, and drainage.",
        "task_name": "Rough Grading",
        "task_description": "Mass earthwork grading for pad preparation across 120 lots, including cut/fill balancing and erosion control.",
        "bid_deadline": "April 15, 2026 at 5:00 PM EST",
        "bid_format": "Lump Sum",
        "document_names": ["Grading Plans v3.pdf", "Geotech Report.pdf"],
        "magic_link_url": "https://portal.bluonx.com/bid/abc123def456",
        "pm_name": "Sarah Johnson",
        "pm_email": "sarah.johnson@bluonx.com",
        "company_name": "BluOnX Development",
    }


@pytest.fixture()
def reminder_context() -> dict:
    """Context for bid reminder templates."""
    return {
        "vendor_contact_name": "John Smith",
        "project_name": "Sunset Ridge Phase 2",
        "task_name": "Rough Grading",
        "bid_deadline": "April 15, 2026 at 5:00 PM EST",
        "magic_link_url": "https://portal.bluonx.com/bid/abc123def456",
        "pm_name": "Sarah Johnson",
        "pm_email": "sarah.johnson@bluonx.com",
        "company_name": "BluOnX Development",
    }


# ── TemplateRenderer ───────────────────────────────────────────────────────


class TestTemplateRenderer:
    """Tests for the TemplateRenderer service itself."""

    def test_renderer_initializes(self):
        assert template_renderer is not None
        assert hasattr(template_renderer, "render")
        assert hasattr(template_renderer, "render_text")

    def test_missing_template_raises(self):
        with pytest.raises(TemplateNotFound):
            template_renderer.render("nonexistent.html", {})

    def test_missing_text_template_raises(self):
        with pytest.raises(TemplateNotFound):
            template_renderer.render_text("nonexistent.txt", {})


# ── Bid Invitation HTML ───────────────────────────────────────────────────


class TestBidInvitationHTML:
    """Tests for the bid invitation HTML template."""

    def test_renders_with_full_context(self, invitation_context):
        result = template_renderer.render("bid_invitation.html", invitation_context)
        assert result
        assert "<!DOCTYPE" in result
        assert "</html>" in result

    def test_magic_link_url_present(self, invitation_context):
        result = template_renderer.render("bid_invitation.html", invitation_context)
        assert invitation_context["magic_link_url"] in result

    def test_vendor_name_present(self, invitation_context):
        result = template_renderer.render("bid_invitation.html", invitation_context)
        assert "John Smith" in result

    def test_project_details_present(self, invitation_context):
        result = template_renderer.render("bid_invitation.html", invitation_context)
        assert "Sunset Ridge Phase 2" in result
        assert "Austin, TX" in result

    def test_bid_details_present(self, invitation_context):
        result = template_renderer.render("bid_invitation.html", invitation_context)
        assert "Rough Grading" in result
        assert "April 15, 2026 at 5:00 PM EST" in result
        assert "Lump Sum" in result

    def test_document_names_listed(self, invitation_context):
        result = template_renderer.render("bid_invitation.html", invitation_context)
        assert "Grading Plans v3.pdf" in result
        assert "Geotech Report.pdf" in result

    def test_optional_fields_none(self, invitation_context):
        invitation_context["project_description"] = None
        invitation_context["task_description"] = None
        invitation_context["document_names"] = []
        result = template_renderer.render("bid_invitation.html", invitation_context)
        assert result
        assert "None" not in result

    def test_default_company_name(self, invitation_context):
        del invitation_context["company_name"]
        result = template_renderer.render("bid_invitation.html", invitation_context)
        assert "BluOnX Development LLC" in result

    def test_html_structure(self, invitation_context):
        result = template_renderer.render("bid_invitation.html", invitation_context)
        assert 'role="presentation"' in result
        assert "Submit Your Bid" in result
        # Bulletproof button VML for Outlook
        assert "v:roundrect" in result

    def test_pm_contact_present(self, invitation_context):
        result = template_renderer.render("bid_invitation.html", invitation_context)
        assert "Sarah Johnson" in result
        assert "sarah.johnson@bluonx.com" in result

    def test_size_under_100kb(self, invitation_context):
        result = template_renderer.render("bid_invitation.html", invitation_context)
        assert len(result.encode("utf-8")) < 100_000

    def test_logo_fallback_when_no_url(self, invitation_context):
        result = template_renderer.render("bid_invitation.html", invitation_context)
        assert "<img" not in result
        # Text fallback should be present
        assert "BluOnX" in result

    def test_logo_img_when_url_provided(self, invitation_context):
        invitation_context["logo_url"] = "https://cdn.bluonx.com/logo.png"
        result = template_renderer.render("bid_invitation.html", invitation_context)
        assert '<img src="https://cdn.bluonx.com/logo.png"' in result
        assert 'alt="BluOnX"' in result


# ── Bid Invitation TXT ────────────────────────────────────────────────────


class TestBidInvitationTXT:
    """Tests for the bid invitation plain-text template."""

    def test_renders_with_full_context(self, invitation_context):
        result = template_renderer.render_text("bid_invitation.txt", invitation_context)
        assert result
        assert len(result) > 100

    def test_no_html_tags(self, invitation_context):
        result = template_renderer.render_text("bid_invitation.txt", invitation_context)
        assert "<table" not in result
        assert "<td" not in result
        assert "<div" not in result
        assert "</html>" not in result

    def test_section_separators(self, invitation_context):
        result = template_renderer.render_text("bid_invitation.txt", invitation_context)
        assert "---" in result or "===" in result

    def test_magic_link_url_present(self, invitation_context):
        result = template_renderer.render_text("bid_invitation.txt", invitation_context)
        assert invitation_context["magic_link_url"] in result

    def test_content_present(self, invitation_context):
        result = template_renderer.render_text("bid_invitation.txt", invitation_context)
        assert "John Smith" in result
        assert "Rough Grading" in result
        assert "Sunset Ridge Phase 2" in result
        assert "Lump Sum" in result

    def test_optional_fields_none(self, invitation_context):
        invitation_context["project_description"] = None
        invitation_context["task_description"] = None
        invitation_context["document_names"] = []
        result = template_renderer.render_text("bid_invitation.txt", invitation_context)
        assert result
        assert "None" not in result


# ── Reminder Templates ─────────────────────────────────────────────────────


REMINDER_TEMPLATES = [
    "bid_reminder_friendly",
    "bid_reminder_urgent",
    "bid_reminder_final",
]


class TestReminderTemplates:
    """Tests for all three bid reminder templates (HTML and TXT)."""

    @pytest.mark.parametrize("template_name", REMINDER_TEMPLATES)
    def test_html_renders(self, reminder_context, template_name):
        result = template_renderer.render(f"{template_name}.html", reminder_context)
        assert result
        assert "<!DOCTYPE" in result
        assert "</html>" in result

    @pytest.mark.parametrize("template_name", REMINDER_TEMPLATES)
    def test_txt_renders(self, reminder_context, template_name):
        result = template_renderer.render_text(f"{template_name}.txt", reminder_context)
        assert result
        assert "<table" not in result

    @pytest.mark.parametrize("template_name", REMINDER_TEMPLATES)
    def test_html_contains_magic_link(self, reminder_context, template_name):
        result = template_renderer.render(f"{template_name}.html", reminder_context)
        assert reminder_context["magic_link_url"] in result

    @pytest.mark.parametrize("template_name", REMINDER_TEMPLATES)
    def test_txt_contains_magic_link(self, reminder_context, template_name):
        result = template_renderer.render_text(f"{template_name}.txt", reminder_context)
        assert reminder_context["magic_link_url"] in result

    @pytest.mark.parametrize("template_name", REMINDER_TEMPLATES)
    def test_html_contains_cta_button(self, reminder_context, template_name):
        result = template_renderer.render(f"{template_name}.html", reminder_context)
        assert "Submit Your Bid" in result
        assert "v:roundrect" in result

    @pytest.mark.parametrize("template_name", REMINDER_TEMPLATES)
    def test_html_contains_deadline(self, reminder_context, template_name):
        result = template_renderer.render(f"{template_name}.html", reminder_context)
        assert reminder_context["bid_deadline"] in result

    @pytest.mark.parametrize("template_name", REMINDER_TEMPLATES)
    def test_html_default_company_name(self, reminder_context, template_name):
        ctx = {k: v for k, v in reminder_context.items() if k != "company_name"}
        result = template_renderer.render(f"{template_name}.html", ctx)
        assert "BluOnX Development LLC" in result

    @pytest.mark.parametrize("template_name", REMINDER_TEMPLATES)
    def test_html_size_under_100kb(self, reminder_context, template_name):
        result = template_renderer.render(f"{template_name}.html", reminder_context)
        assert len(result.encode("utf-8")) < 100_000


class TestReminderUrgencyStyles:
    """Tests that urgency levels have appropriate visual indicators."""

    def test_friendly_has_no_alert_banner(self, reminder_context):
        result = template_renderer.render("bid_reminder_friendly.html", reminder_context)
        assert "#f8d7da" not in result  # No red alert
        assert "#fff3cd" not in result  # No yellow alert

    def test_urgent_has_yellow_alert(self, reminder_context):
        result = template_renderer.render("bid_reminder_urgent.html", reminder_context)
        assert "#fff3cd" in result  # Yellow alert background
        assert "#ffc107" in result  # Yellow border

    def test_final_has_red_alert(self, reminder_context):
        result = template_renderer.render("bid_reminder_final.html", reminder_context)
        assert "#f8d7da" in result  # Red alert background
        assert "#dc3545" in result  # Red border


# ── Sample Output ──────────────────────────────────────────────────────────


class TestSampleOutput:
    """Saves rendered templates to tmp_path for visual inspection in a browser."""

    ALL_TEMPLATES = [
        ("bid_invitation.html", "html"),
        ("bid_invitation.txt", "txt"),
        ("bid_reminder_friendly.html", "html"),
        ("bid_reminder_friendly.txt", "txt"),
        ("bid_reminder_urgent.html", "html"),
        ("bid_reminder_urgent.txt", "txt"),
        ("bid_reminder_final.html", "html"),
        ("bid_reminder_final.txt", "txt"),
    ]

    def test_save_rendered_samples(self, tmp_path, invitation_context, reminder_context):
        """Render all templates and save to tmp_path for manual inspection."""
        invitation_templates = [t for t in self.ALL_TEMPLATES if "invitation" in t[0]]
        reminder_templates = [t for t in self.ALL_TEMPLATES if "reminder" in t[0]]

        for template_name, fmt in invitation_templates:
            if fmt == "html":
                content = template_renderer.render(template_name, invitation_context)
            else:
                content = template_renderer.render_text(template_name, invitation_context)
            output_file = tmp_path / template_name
            output_file.write_text(content, encoding="utf-8")
            assert output_file.exists()

        for template_name, fmt in reminder_templates:
            if fmt == "html":
                content = template_renderer.render(template_name, reminder_context)
            else:
                content = template_renderer.render_text(template_name, reminder_context)
            output_file = tmp_path / template_name
            output_file.write_text(content, encoding="utf-8")
            assert output_file.exists()

        # Print the tmp_path so the developer can find the rendered files
        print(f"\nRendered email samples saved to: {tmp_path}")
