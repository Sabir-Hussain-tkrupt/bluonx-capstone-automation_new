"""
Jinja2 email template rendering service.

Loads templates from backend/app/templates/emails/ and renders them
with context variables. Used by the email sending service (Task 4.3)
to produce HTML and plain-text email bodies.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "emails"


class TemplateRenderer:
    """Renders Jinja2 email templates to HTML or plain text."""

    def __init__(self, template_dir: Path = _TEMPLATE_DIR) -> None:
        self._html_env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._text_env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, template_name: str, context: dict) -> str:
        """Render an HTML email template with the given context."""
        template = self._html_env.get_template(template_name)
        return template.render(**context)

    def render_text(self, template_name: str, context: dict) -> str:
        """Render a plain-text email template with the given context."""
        template = self._text_env.get_template(template_name)
        return template.render(**context)


template_renderer = TemplateRenderer()
