"""Turning a context into HTML and PDF, and choosing which template to use.

Templates live in the database so they are versioned, can differ per bank,
and are edited by admins (CLAUDE.md §5). Because of that they are rendered in
a Jinja *sandbox*: a template is data an admin types in, and must not be able
to reach Python internals from inside the report.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment
from markupsafe import Markup, escape

from .models import ReportTemplate

DEFAULT_NAME = "Standard valuation report"
DEFAULT_DIR = Path(__file__).parent / "default_template"


class PdfEngineUnavailable(Exception):
    """WeasyPrint is installed but its native libraries (Pango) are not."""


def _css_string(value) -> str:
    """Safe inside a quoted CSS string: no quote, backslash, newline or `<`
    can end the string or the <style> block."""
    out = str(value)
    for char, escaped in (("\\", "\\\\"), ('"', '\\"'), ("\n", " "), ("\r", " "), ("<", "\\3c ")):
        out = out.replace(char, escaped)
    return out


def _paragraphs(text) -> Markup:
    """Report text as paragraphs, with lines starting "- " as bullet points.
    Escaped first: the text is the valuer's, not markup."""
    out = []
    for block in str(text or "").replace("\r\n", "\n").split("\n\n"):
        # Runs of plain lines and of bullet lines, in order.
        runs: list[tuple[bool, list[str]]] = []
        for line in (x.strip() for x in block.split("\n") if x.strip()):
            bullet = line.startswith(("- ", "• "))
            item = line[2:].strip() if bullet else line
            if runs and runs[-1][0] == bullet:
                runs[-1][1].append(item)
            else:
                runs.append((bullet, [item]))
        for bullet, items in runs:
            if bullet:
                out.append("<ul>" + "".join(f"<li>{escape(x)}</li>" for x in items) + "</ul>")
            else:
                out.append("<p>" + "<br>".join(str(escape(x)) for x in items) + "</p>")
    return Markup("".join(out))


def _environment() -> SandboxedEnvironment:
    env = SandboxedEnvironment(autoescape=True, undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
    env.filters["cssstr"] = _css_string
    env.filters["paras"] = _paragraphs
    return env


# --- the shipped default template ---------------------------------------------------


def ensure_default_template() -> ReportTemplate:
    """The template that ships with the code, stored in the database.

    Its version is a hash of its content, so changing the shipped files
    creates a new version instead of silently rewriting the one old reports
    were rendered with, and an admin's edits to a stored row are never
    overwritten by this."""
    html = (DEFAULT_DIR / "report.html.j2").read_text()
    css = (DEFAULT_DIR / "report.css").read_text()
    digest = hashlib.sha256((html + css).encode()).hexdigest()[:8]
    template, _ = ReportTemplate.objects.get_or_create(
        name=DEFAULT_NAME, version=f"v1-{digest}", bank=None, defaults={"html": html, "css": css},
    )
    return template


def choose_template(job) -> ReportTemplate:
    """Which template renders this job.

    In order: the job's own choice; an admin-authored template for its bank;
    an admin-authored generic one; the shipped default. Older stored copies of
    the shipped default are never picked here (a job that was issued on one
    keeps pointing at it through `job.report_template`), so editing the shipped
    files really does change what new reports use."""
    current_default = ensure_default_template()
    if job.report_template_id and job.report_template.active:
        return job.report_template
    authored = ReportTemplate.objects.filter(active=True).exclude(name=DEFAULT_NAME).order_by("-created_at", "-id")
    return (
        authored.filter(bank=job.bank).first()
        or authored.filter(bank__isnull=True).first()
        or current_default
    )


# --- rendering --------------------------------------------------------------------------


def render_html(template: ReportTemplate, context: dict) -> str:
    env = _environment()
    css = env.from_string(template.css).render(
        firm_name=context["firm"]["name"], ref_no=context["meta"]["ref_no"], is_draft=context["meta"]["is_draft"]
    )
    # The stylesheet is trusted template content, not report data: it must not
    # be HTML-escaped (that would turn its quotes into entities).
    from .media import resolve_media  # reads the stored files; only the template needs the results

    return env.from_string(template.html).render(css=Markup(css), **resolve_media(context)).lstrip()


def pdf_engine_available() -> bool:
    try:
        import weasyprint  # noqa: F401
    except (OSError, ImportError):
        return False
    return True


def render_pdf(html: str) -> bytes:
    try:
        from weasyprint import HTML
    except (OSError, ImportError) as exc:
        raise PdfEngineUnavailable(
            "The PDF engine can't load its system libraries (Pango). "
            "Install them (macOS: `brew install pango`) and try again."
        ) from exc
    return HTML(string=html, url_fetcher=embedded_only_fetcher()).write_pdf()


def embedded_only_fetcher():
    """Everything a report shows is embedded as a data: URI. Templates are
    editable in the admin, so nothing else is fetched: no local files, no
    network."""
    from weasyprint.urls import URLFetcher

    return URLFetcher(allowed_protocols={"data"}, allow_redirects=False)
