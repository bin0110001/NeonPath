"""Deterministic application-tailoring recommendations (plan section 13). Pure logic.

Principles: recommend, never rewrite. Every recommendation names the profile record it
rests on; anything the profile cannot back is reported as missing evidence. Nothing here
invents experience or alters a verified fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from careerflow.domain.evaluations.service import contains_term, tokens

TAILOR_VERSION = "tailor-v1"
MAX_ACHIEVEMENTS = 5


@dataclass(frozen=True)
class SkillFact:
    id: str
    name: str
    aliases: tuple[str, ...] = ()
    category: str | None = None
    years: float | None = None
    verified: bool = False


@dataclass(frozen=True)
class AchievementFact:
    id: str
    title: str
    text: str = ""  # situation + action + result
    technologies: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    verified: bool = False


@dataclass(frozen=True)
class VariantFact:
    id: str
    name: str
    role_family: str | None = None
    skill_categories: tuple[str, ...] = ()
    achievement_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class JobFacts:
    title: str
    description: str
    required_skills: tuple[str, ...] = ()  # extracted or catalogue-detected skill names
    preferred_skills: tuple[str, ...] = ()


@dataclass(frozen=True)
class Note:
    """One recommendation, with the profile records it is based on."""

    text: str
    evidence_ids: tuple[str, ...] = ()  # e.g. "achievement:<id>", "skill:<id>"


@dataclass
class Recommendation:
    variant_id: str | None = None
    achievement_ids: list[str] = field(default_factory=list)
    skill_order: list[str] = field(default_factory=list)
    summary_suggestion: str | None = None
    tailoring_notes: list[Note] = field(default_factory=list)
    cover_letter_notes: list[Note] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _job_text(job: JobFacts) -> str:
    return f"{job.title}\n{job.description}\n" + "\n".join([*job.required_skills, *job.preferred_skills])


def _skill_hit(skill: SkillFact, text: str) -> bool:
    return any(contains_term(text, term) for term in (skill.name, *skill.aliases))


def _achievement_score(a: AchievementFact, job: JobFacts, text: str) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    for tech in a.technologies:
        if contains_term(text, tech):
            score += 2.0
            reasons.append(tech)
    for tag in a.tags:
        if contains_term(text, tag):
            score += 1.0
            reasons.append(tag)
    title_words = {w for w in tokens(a.title) if len(w) > 3}
    score += 0.5 * len(title_words & set(tokens(text)))
    for required in job.required_skills:  # an achievement that evidences a required skill matters most
        if contains_term(f"{a.title} {a.text} {' '.join(a.technologies)}", required):
            score += 3.0
            reasons.append(required)
    return score, list(dict.fromkeys(reasons))


def _variant_score(v: VariantFact, job: JobFacts, text: str, skills: list[SkillFact]) -> float:
    score = 0.0
    if v.role_family and contains_term(job.title, v.role_family):
        score += 3.0
    elif v.role_family:
        words = [w for w in tokens(v.role_family) if len(w) >= 3]
        score += 1.5 * sum(w in tokens(job.title) for w in words) / max(len(words), 1)
    wanted = {c.lower() for c in v.skill_categories}
    score += sum(1.0 for s in skills if s.category and s.category.lower() in wanted and _skill_hit(s, text))
    return score


def recommend(
    job: JobFacts,
    skills: list[SkillFact],
    achievements: list[AchievementFact],
    variants: list[VariantFact],
    known_skill_names: list[str] | None = None,
) -> Recommendation:
    text = _job_text(job)
    rec = Recommendation()

    # 1. variant: the best fit for this job, if any variants exist
    if variants:
        ranked = sorted(variants, key=lambda v: (-_variant_score(v, job, text, skills), v.name))
        best = ranked[0]
        rec.variant_id = best.id
        rec.tailoring_notes.append(Note(f"Use the '{best.name}' resume variant."))

    # 2. achievements: ranked by relevance; a chosen variant's selection breaks ties
    preferred = set(next((v.achievement_ids for v in variants if v.id == rec.variant_id), ()))
    scored = []
    for a in achievements:
        score, reasons = _achievement_score(a, job, text)
        if score > 0:
            scored.append((score + (0.25 if a.id in preferred else 0.0), a, reasons))
    scored.sort(key=lambda item: (-item[0], item[1].title))
    for _, a, reasons in scored[:MAX_ACHIEVEMENTS]:
        rec.achievement_ids.append(a.id)
        rec.tailoring_notes.append(
            Note(f"Feature the achievement '{a.title}' (matches: {', '.join(reasons)}).", (f"achievement:{a.id}",))
        )
        rec.cover_letter_notes.append(
            Note(f"Talk about '{a.title}' to show {', '.join(reasons[:3])}.", (f"achievement:{a.id}",))
        )
        if not a.verified:
            rec.warnings.append(f"Achievement '{a.title}' is not marked verified; confirm it before using it.")

    # 3. skill order: skills the job mentions first, then by years of experience
    variant_categories = {
        c.lower() for v in variants if v.id == rec.variant_id for c in v.skill_categories
    }

    def skill_key(s: SkillFact) -> tuple[int, int, float, str]:
        hit = 0 if _skill_hit(s, text) else 1
        categorised = 0 if (s.category or "").lower() in variant_categories else 1
        return hit, categorised, -(s.years or 0.0), s.name.lower()

    ordered = sorted(skills, key=skill_key)
    rec.skill_order = [s.name for s in ordered]
    matched = [s for s in ordered if _skill_hit(s, text)]
    for skill in matched:
        if not skill.verified:
            rec.warnings.append(f"Skill '{skill.name}' is not marked verified.")

    # 4. missing evidence: required skills with neither a skill record nor an achievement behind them
    held = [*skills]
    for required in dict.fromkeys([*job.required_skills]):
        has_skill = any(_skill_hit(s, required) or contains_term(required, s.name) for s in held)
        has_achievement = any(
            contains_term(f"{a.title} {a.text} {' '.join(a.technologies)}", required) for a in achievements
        )
        if not has_skill and not has_achievement:
            rec.missing_evidence.append(f"No profile evidence for required skill: {required}")
    for name in known_skill_names or []:
        if (
            contains_term(text, name)
            and name not in job.required_skills
            and not any(_skill_hit(s, name) for s in held)
            and f"No profile evidence for required skill: {name}" not in rec.missing_evidence
        ):
            rec.missing_evidence.append(f"The job mentions {name}, which your profile does not show")

    # 5. summary suggestion: assembled only from real records, flagged as a suggestion
    parts = []
    if matched:
        parts.append("emphasise " + ", ".join(s.name for s in matched[:4]))
    if rec.achievement_ids:
        top = next(a for a in achievements if a.id == rec.achievement_ids[0])
        parts.append(f"open with '{top.title}'")
    if parts:
        rec.summary_suggestion = f"For '{job.title}': " + " and ".join(parts) + "."
        rec.tailoring_notes.append(
            Note(
                "Summary suggestion built from your own records; edit freely.",
                tuple(f"skill:{s.id}" for s in matched[:4])
                + tuple(f"achievement:{i}" for i in rec.achievement_ids[:1]),
            )
        )
    return rec
