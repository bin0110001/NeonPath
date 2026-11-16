"""Markdown and HTML renderers. Output is deterministic: same document, same bytes."""

from __future__ import annotations

from html import escape

from careerflow.domain.artifacts.ports import ResumeDocument


def _contact_lines(document: ResumeDocument) -> list[str]:
    c = document.contact
    if c is None:
        return []
    parts = [p for p in (c.email, c.phone, c.location, *c.links) if p]
    return [" · ".join(parts)] if parts else []


def _md(text: str) -> str:
    """Neutralise raw HTML in profile text: Markdown viewers may pass `<tag>` straight through."""
    return text.replace("<", r"\<").replace(">", r"\>")


class MarkdownRenderer:
    format = "markdown"
    content_type = "text/markdown; charset=utf-8"
    extension = "md"
    version = "md-1"

    def render(self, document: ResumeDocument) -> bytes:
        lines = [f"# {_md(document.name)}"]
        if document.headline:
            lines.append(f"*{_md(document.headline)}*")
        lines += _contact_lines(document)
        if document.target:
            lines += ["", f"_Prepared for: {_md(document.target)}_"]
        if document.summary:
            lines += ["", "## Summary", _md(document.summary)]
        if document.skills:
            lines += ["", "## Skills", _md(", ".join(document.skills))]
        if document.experiences:
            lines += ["", "## Experience"]
            for e in document.experiences:
                header = f"### {_md(e.title)}, {_md(e.organization)}"
                lines += [header, _md(" · ".join(p for p in (e.dates, e.location) if p)), _md(e.description or "")]
        if document.achievements:
            lines += ["", "## Achievements"]
            for a in document.achievements:
                tech = f" _({', '.join(a.technologies)})_" if a.technologies else ""
                lines.append(f"- **{_md(a.title)}**{_md(tech)}" + (f": {_md(a.detail)}" if a.detail else ""))
        if document.education:
            lines += ["", "## Education"]
            for ed in document.education:
                detail = ", ".join(p for p in (ed.degree, ed.field_of_study) if p)
                lines.append(f"- {_md(ed.institution)}" + (f": {_md(detail)}" if detail else "") + (f" ({ed.dates})" if ed.dates else ""))
        if document.cover_letter_notes:
            lines += ["", "## Cover letter notes"] + [f"- {_md(n)}" for n in document.cover_letter_notes]
        return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


class HtmlRenderer:
    """Every value is escaped: profile text can never inject markup or script."""

    format = "html"
    content_type = "text/html; charset=utf-8"
    extension = "html"
    version = "html-1"

    def render(self, document: ResumeDocument) -> bytes:
        e = escape
        out = [
            "<!DOCTYPE html>",
            '<html lang="en"><head><meta charset="utf-8">',
            f"<title>{e(document.name)}</title>",
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<style>body{font-family:sans-serif;max-width:46rem;margin:2rem auto;line-height:1.45}"
            "h1{margin-bottom:0}h2{border-bottom:1px solid #ccc}</style></head><body>",
            f"<h1>{e(document.name)}</h1>",
        ]
        if document.headline:
            out.append(f"<p><em>{e(document.headline)}</em></p>")
        for line in _contact_lines(document):
            out.append(f"<p>{e(line)}</p>")
        if document.target:
            out.append(f"<p><small>Prepared for: {e(document.target)}</small></p>")
        if document.summary:
            out.append(f"<h2>Summary</h2><p>{e(document.summary)}</p>")
        if document.skills:
            out.append(f"<h2>Skills</h2><p>{e(', '.join(document.skills))}</p>")
        if document.experiences:
            out.append("<h2>Experience</h2>")
            for x in document.experiences:
                meta = " · ".join(p for p in (x.dates, x.location) if p)
                out.append(f"<h3>{e(x.title)}, {e(x.organization)}</h3>")
                if meta:
                    out.append(f"<p><small>{e(meta)}</small></p>")
                if x.description:
                    out.append(f"<p>{e(x.description)}</p>")
        if document.achievements:
            out.append("<h2>Achievements</h2><ul>")
            for a in document.achievements:
                tech = f" <em>({e(', '.join(a.technologies))})</em>" if a.technologies else ""
                out.append(f"<li><strong>{e(a.title)}</strong>{tech}" + (f": {e(a.detail)}" if a.detail else "") + "</li>")
            out.append("</ul>")
        if document.education:
            out.append("<h2>Education</h2><ul>")
            for ed in document.education:
                detail = ", ".join(p for p in (ed.degree, ed.field_of_study) if p)
                out.append(f"<li>{e(ed.institution)}" + (f": {e(detail)}" if detail else "") + (f" ({e(ed.dates)})" if ed.dates else "") + "</li>")
            out.append("</ul>")
        if document.cover_letter_notes:
            out.append("<h2>Cover letter notes</h2><ul>" + "".join(f"<li>{e(n)}</li>" for n in document.cover_letter_notes) + "</ul>")
        out.append("</body></html>")
        return ("\n".join(out) + "\n").encode("utf-8")
