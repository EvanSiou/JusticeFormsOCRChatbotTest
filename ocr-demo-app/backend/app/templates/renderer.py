"""Jinja2-based form template renderer."""
import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent
_env = None


def _get_env():
    global _env
    if _env is None:
        _env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    return _env


TEMPLATE_MAP = {
    "prisoner_registration": "prisoner_registration.html",
    "affidavit_financial": "affidavit_financial.html",
}


def render_form_template(
    form_type: str,
    classified_fields: list[dict],
    threshold: float = 0.6,
) -> str:
    """Render an HTML template populated with classified field values.

    Args:
        form_type: Form type ID (e.g., 'prisoner_registration')
        classified_fields: List of classified field dicts with field_type, value, confidence
        threshold: Quality threshold for confidence highlighting

    Returns:
        Rendered HTML string
    """
    template_name = TEMPLATE_MAP.get(form_type)
    if not template_name:
        logger.warning(f"No template for form type: {form_type}")
        return _render_generic(classified_fields, threshold)

    template_path = TEMPLATE_DIR / template_name
    if not template_path.exists():
        logger.warning(f"Template file not found: {template_path}")
        return _render_generic(classified_fields, threshold)

    env = _get_env()
    template = env.get_template(template_name)

    # Convert fields list to dict keyed by field_type
    fields = {}
    for i, f in enumerate(classified_fields):
        ft = f.get("field_type", f"field_{i}")
        conf = f.get("confidence", 0)
        fields[ft] = {
            "value": f.get("value", ""),
            "confidence": conf,
            "level": "high" if conf >= 0.95 else "low",
            "index": i,
        }

    return template.render(fields=fields, threshold=threshold)


def _render_generic(classified_fields: list[dict], threshold: float) -> str:
    """Fallback: render fields as a simple HTML table."""
    rows = []
    for i, f in enumerate(classified_fields):
        conf = f.get("confidence", 0)
        level = "high" if conf >= 0.8 else "medium" if conf >= threshold else "low"
        color = {"high": "#22c55e", "medium": "#eab308", "low": "#ef4444"}[level]
        rows.append(
            f'<tr>'
            f'<td style="padding:4px 8px;border:1px solid #ddd;font-weight:600">{f.get("field_type", "")}</td>'
            f'<td style="padding:4px 8px;border:1px solid #ddd" '
            f'contenteditable="true" data-field-index="{i}">{f.get("value", "")}</td>'
            f'<td style="padding:4px 8px;border:1px solid #ddd;text-align:center">'
            f'<span style="background:{color};color:white;padding:2px 6px;border-radius:4px;font-size:11px">'
            f'{conf*100:.0f}%</span></td>'
            f'</tr>'
        )

    return (
        '<table style="width:100%;border-collapse:collapse;font-family:sans-serif;font-size:13px">'
        '<thead><tr>'
        '<th style="padding:6px 8px;border:1px solid #ddd;background:#f3f4f6;text-align:left">Field</th>'
        '<th style="padding:6px 8px;border:1px solid #ddd;background:#f3f4f6;text-align:left">Value</th>'
        '<th style="padding:6px 8px;border:1px solid #ddd;background:#f3f4f6;text-align:center">Confidence</th>'
        '</tr></thead><tbody>'
        + "\n".join(rows)
        + '</tbody></table>'
    )
