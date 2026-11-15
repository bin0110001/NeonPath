"""Deterministic requirement extraction used when AI is disabled (no LLM, no frameworks).

Intentionally simple and conservative: it finds known skills, required-vs-preferred
sections, a seniority level and architecture/leadership/management cues.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from careerflow.domain.evaluations.service import SENIORITY_LEVELS, contains_term, tokens
from careerflow.domain.profiles.model import SkillInfo

PREFERRED_MARKERS = ("preferred", "nice to have", "nice-to-have", "bonus", "plus", "desirable")
REQUIRED_MARKERS = ("required", "requirements", "must have", "must-have", "qualifications", "you have")

CUES: dict[str, tuple[str, ...]] = {
    "architecture": ("architect", "system design", "distributed system", "technical design"),
    "leadership": ("lead ", "leading", "mentor", "technical leadership", "set direction"),
    "management": ("manage a team", "people management", "direct reports", "hiring", "line manage"),
    "travel": ("travel",),
}


@dataclass(frozen=True)
class KeywordItem:
    text: str
    source_quote: str
    confidence: float


@dataclass
class KeywordExtraction:
    required_skills: list[KeywordItem] = field(default_factory=list)
    preferred_skills: list[KeywordItem] = field(default_factory=list)
    architecture: list[KeywordItem] = field(default_factory=list)
    leadership: list[KeywordItem] = field(default_factory=list)
    management: list[KeywordItem] = field(default_factory=list)
    travel: list[KeywordItem] = field(default_factory=list)
    inferred_seniority: str | None = None


def _sections(description: str) -> list[tuple[str, str]]:
    """Split into (section_kind, line) pairs; kind is 'preferred', 'required' or 'general'."""
    kind = "general"
    out: list[tuple[str, str]] = []
    for raw in description.splitlines():
        line = raw.strip(" \t-*•")
        if not line:
            continue
        lowered = line.lower()
        is_heading = len(line) < 60 and (line.endswith(":") or line.isupper() or lowered.istitle())
        if is_heading or len(line) < 40:
            if any(m in lowered for m in PREFERRED_MARKERS):
                kind = "preferred"
                continue
            if any(m in lowered for m in REQUIRED_MARKERS):
                kind = "required"
                continue
        out.append((kind, line))
    return out


def _quote(line: str) -> str:
    return line if len(line) <= 160 else line[:157] + "..."


def extract_keywords(title: str, description: str, catalog: list[SkillInfo]) -> KeywordExtraction:
    result = KeywordExtraction()
    seen: set[str] = set()
    for kind, line in _sections(description):
        lowered = line.lower()
        # sentences that say "preferred"/"nice to have" inline count as preferred too
        inline_preferred = any(m in lowered for m in PREFERRED_MARKERS)
        for skill in catalog:
            if skill.name.lower() in seen:
                continue
            if any(contains_term(line, term) for term in [skill.name, *skill.aliases]):
                seen.add(skill.name.lower())
                item = KeywordItem(skill.name, _quote(line), 0.6)
                if kind == "preferred" or inline_preferred:
                    result.preferred_skills.append(item)
                else:
                    result.required_skills.append(item)
        for label, cues in CUES.items():
            if any(cue in lowered + " " for cue in cues):
                target = getattr(result, label)
                if not target:  # one representative line per cue family
                    target.append(KeywordItem(_quote(line), _quote(line), 0.5))
    levels = [lvl for lvl, markers in SENIORITY_LEVELS.items() if set(tokens(title)) & markers]
    if levels:
        result.inferred_seniority = levels[0]
    else:
        match = re.search(r"(\d+)\+?\s+years", description.lower())
        if match:
            years = int(match.group(1))
            result.inferred_seniority = "entry" if years < 2 else "mid" if years < 5 else "senior"
    return result
