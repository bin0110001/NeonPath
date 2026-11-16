"""Renderer registry: add a format by registering a renderer here."""

from __future__ import annotations

from careerflow.domain.artifacts.ports import ArtifactRenderer
from careerflow.infrastructure.artifacts.binary_renderers import DocxRenderer, PdfRenderer
from careerflow.infrastructure.artifacts.text_renderers import HtmlRenderer, MarkdownRenderer

RENDERERS: dict[str, ArtifactRenderer] = {
    r.format: r for r in (MarkdownRenderer(), HtmlRenderer(), DocxRenderer(), PdfRenderer())
}


class UnknownFormatError(ValueError):
    pass


def get_renderer(fmt: str) -> ArtifactRenderer:
    try:
        return RENDERERS[fmt]
    except KeyError:
        raise UnknownFormatError(f"unknown format {fmt!r}; available: {sorted(RENDERERS)}") from None
