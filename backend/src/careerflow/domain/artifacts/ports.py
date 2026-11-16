"""Artifact rendering port (plan section 13).

A ``ResumeDocument`` is the complete, JSON-serialisable *generation input*. Rendering is a
pure function of it, so any stored version can be reproduced exactly from retained inputs.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ContactBlock:
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExperienceBlock:
    title: str
    organization: str
    dates: str = ""
    location: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class AchievementBlock:
    title: str
    detail: str = ""
    technologies: tuple[str, ...] = ()
    verified: bool = False


@dataclass(frozen=True)
class EducationBlock:
    institution: str
    degree: str | None = None
    field_of_study: str | None = None
    dates: str = ""


@dataclass(frozen=True)
class ResumeDocument:
    name: str
    headline: str | None = None
    summary: str | None = None
    contact: ContactBlock | None = None
    skills: tuple[str, ...] = ()
    experiences: tuple[ExperienceBlock, ...] = ()
    achievements: tuple[AchievementBlock, ...] = ()
    education: tuple[EducationBlock, ...] = ()
    cover_letter_notes: tuple[str, ...] = ()
    target: str | None = None  # "Title at Company" the document was prepared for
    redacted: bool = False

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ResumeDocument:
        contact = data.get("contact")
        return cls(
            name=data["name"],
            headline=data.get("headline"),
            summary=data.get("summary"),
            contact=ContactBlock(**{**contact, "links": tuple(contact.get("links", ()))}) if contact else None,
            skills=tuple(data.get("skills", ())),
            experiences=tuple(ExperienceBlock(**e) for e in data.get("experiences", ())),
            achievements=tuple(
                AchievementBlock(**{**a, "technologies": tuple(a.get("technologies", ()))})
                for a in data.get("achievements", ())
            ),
            education=tuple(EducationBlock(**e) for e in data.get("education", ())),
            cover_letter_notes=tuple(data.get("cover_letter_notes", ())),
            target=data.get("target"),
            redacted=bool(data.get("redacted", False)),
        )


class ArtifactRenderer(Protocol):
    format: str  # "markdown", "html", "docx", "pdf"
    content_type: str
    extension: str
    version: str  # bump when output changes; stored with every artifact

    def render(self, document: ResumeDocument) -> bytes: ...


@dataclass
class RenderedArtifact:
    renderer: str
    version: str
    content: bytes
    sha256: str = field(default="")


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?<!\w)[+(]?\d[\d\s().-]{7,}\d(?!\w)")
_URL = re.compile(r"https?://\S+|www\.\S+")


def scrub_contact_details(text: str | None) -> str | None:
    """Remove e-mail addresses, phone numbers and URLs from free text (redacted mode)."""
    if text is None:
        return None
    def phone(match: re.Match[str]) -> str:
        # date ranges such as "2019 - 2024" look phone-like; real numbers have at least 9 digits
        return "[phone removed]" if sum(c.isdigit() for c in match.group()) >= 9 else match.group()

    return _URL.sub("[link removed]", _PHONE.sub(phone, _EMAIL.sub("[email removed]", text)))


def redact(document: ResumeDocument) -> ResumeDocument:
    """A public copy: no contact block and no contact details hidden in free text."""
    from dataclasses import replace

    return replace(
        document,
        contact=None,
        summary=scrub_contact_details(document.summary),
        experiences=tuple(
            replace(e, description=scrub_contact_details(e.description)) for e in document.experiences
        ),
        achievements=tuple(replace(a, detail=scrub_contact_details(a.detail) or "") for a in document.achievements),
        cover_letter_notes=tuple(scrub_contact_details(n) or "" for n in document.cover_letter_notes),
        redacted=True,
    )
