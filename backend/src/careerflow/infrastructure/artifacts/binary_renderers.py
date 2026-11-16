"""DOCX and PDF renderers: pure-Python libraries, so they work in the slim backend image
under Podman or Docker with no system packages, privileges or network access.

Both are deterministic (fixed metadata, normalised zip timestamps, ReportLab's
``invariant`` mode) so an artifact can be reproduced byte-for-byte from its inputs.

PDF limitation: ReportLab's built-in fonts are Latin-1; other characters render as "?".
Use the DOCX/HTML/Markdown formats for non-Latin text.
"""

from __future__ import annotations

import io
import zipfile
from datetime import datetime
from xml.sax.saxutils import escape

from docx import Document as new_docx
from docx.shared import Pt
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

from careerflow.domain.artifacts.ports import ResumeDocument

FIXED_TIME = datetime(2000, 1, 1)
ZIP_TIME = (2000, 1, 1, 0, 0, 0)


def _meta_lines(document: ResumeDocument) -> list[str]:
    c = document.contact
    if c is None:
        return []
    parts = [p for p in (c.email, c.phone, c.location, *c.links) if p]
    return [" · ".join(parts)] if parts else []


def _normalize_zip(data: bytes) -> bytes:
    """Rewrite a zip with fixed timestamps and a stable entry order."""
    source = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for name in sorted(source.namelist()):
            info = zipfile.ZipInfo(name, ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            target.writestr(info, source.read(name))
    return out.getvalue()


class DocxRenderer:
    format = "docx"
    content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    extension = "docx"
    version = "docx-1"

    def render(self, document: ResumeDocument) -> bytes:
        doc = new_docx()
        props = doc.core_properties
        props.author = "CareerFlow"
        props.title = document.name
        props.created = props.modified = props.last_printed = FIXED_TIME
        props.last_modified_by = "CareerFlow"
        props.revision = 1

        doc.add_heading(document.name, level=0)
        if document.headline:
            doc.add_paragraph(document.headline).runs[0].italic = True
        for line in _meta_lines(document):
            doc.add_paragraph(line)
        if document.target:
            para = doc.add_paragraph(f"Prepared for: {document.target}")
            para.runs[0].font.size = Pt(9)
        if document.summary:
            doc.add_heading("Summary", level=1)
            doc.add_paragraph(document.summary)
        if document.skills:
            doc.add_heading("Skills", level=1)
            doc.add_paragraph(", ".join(document.skills))
        if document.experiences:
            doc.add_heading("Experience", level=1)
            for e in document.experiences:
                doc.add_heading(f"{e.title}, {e.organization}", level=2)
                meta = " · ".join(p for p in (e.dates, e.location) if p)
                if meta:
                    doc.add_paragraph(meta)
                if e.description:
                    doc.add_paragraph(e.description)
        if document.achievements:
            doc.add_heading("Achievements", level=1)
            for a in document.achievements:
                tech = f" ({', '.join(a.technologies)})" if a.technologies else ""
                para = doc.add_paragraph(style="List Bullet")
                para.add_run(a.title).bold = True
                para.add_run(tech + (f": {a.detail}" if a.detail else ""))
        if document.education:
            doc.add_heading("Education", level=1)
            for ed in document.education:
                detail = ", ".join(p for p in (ed.degree, ed.field_of_study) if p)
                doc.add_paragraph(
                    ed.institution + (f": {detail}" if detail else "") + (f" ({ed.dates})" if ed.dates else ""),
                    style="List Bullet",
                )
        if document.cover_letter_notes:
            doc.add_heading("Cover letter notes", level=1)
            for note in document.cover_letter_notes:
                doc.add_paragraph(note, style="List Bullet")
        buffer = io.BytesIO()
        doc.save(buffer)
        return _normalize_zip(buffer.getvalue())


def _latin1(text: str) -> str:
    return text.encode("latin-1", "replace").decode("latin-1")


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(_latin1(text)), style)


class PdfRenderer:
    format = "pdf"
    content_type = "application/pdf"
    extension = "pdf"
    version = "pdf-1"

    def render(self, document: ResumeDocument) -> bytes:
        styles = getSampleStyleSheet()
        body = styles["BodyText"]
        h1, h2, h3 = styles["Title"], styles["Heading2"], styles["Heading3"]
        small = ParagraphStyle("small", parent=body, fontSize=8, textColor="#555555")
        story: list[object] = [_p(document.name, h1)]
        if document.headline:
            story.append(_p(document.headline, body))
        for line in _meta_lines(document):
            story.append(_p(line, body))
        if document.target:
            story.append(_p(f"Prepared for: {document.target}", small))
        if document.summary:
            story += [_p("Summary", h2), _p(document.summary, body)]
        if document.skills:
            story += [_p("Skills", h2), _p(", ".join(document.skills), body)]
        if document.experiences:
            story.append(_p("Experience", h2))
            for e in document.experiences:
                story.append(_p(f"{e.title}, {e.organization}", h3))
                meta = " · ".join(p for p in (e.dates, e.location) if p)
                if meta:
                    story.append(_p(meta, small))
                if e.description:
                    story.append(_p(e.description, body))
        if document.achievements:
            story.append(_p("Achievements", h2))
            items = []
            for a in document.achievements:
                tech = f" ({', '.join(a.technologies)})" if a.technologies else ""
                items.append(ListItem(_p(f"{a.title}{tech}" + (f": {a.detail}" if a.detail else ""), body)))
            story.append(ListFlowable(items, bulletType="bullet"))
        if document.education:
            story.append(_p("Education", h2))
            for ed in document.education:
                detail = ", ".join(p for p in (ed.degree, ed.field_of_study) if p)
                story.append(_p(ed.institution + (f": {detail}" if detail else "") + (f" ({ed.dates})" if ed.dates else ""), body))
        if document.cover_letter_notes:
            story.append(_p("Cover letter notes", h2))
            story.append(ListFlowable([ListItem(_p(n, body)) for n in document.cover_letter_notes], bulletType="bullet"))
        story.append(Spacer(1, 4 * mm))
        buffer = io.BytesIO()
        SimpleDocTemplate(
            buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
            title=_latin1(document.name), author="CareerFlow", invariant=1,
        ).build(story)
        return buffer.getvalue()
