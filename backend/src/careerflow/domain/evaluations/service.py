"""Deterministic evaluation (plan sections 12.1, 12.3, 12.4).

Pure rule-based logic that needs no LLM. Every dimension is derived from its own
signals; when there is no deterministic signal the dimension is reported as
unknown and left out of the weighted score instead of being fabricated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from careerflow.domain.jobs.model import Job
from careerflow.domain.profiles.model import (
    Profile,
    RoleFamily,
    RoleTarget,
    SearchPreferences,
    SkillInfo,
)

EVALUATOR_VERSION = "deterministic-v2.0"

DEFAULT_WEIGHTS: dict[str, float] = {
    "role_alignment": 0.20,
    "seniority_alignment": 0.15,
    "technical_alignment": 0.15,
    "architecture_alignment": 0.15,
    "leadership_alignment": 0.10,
    "domain_alignment": 0.0,
    "location_alignment": 0.10,
    "compensation_alignment": 0.10,
    "employment_alignment": 0.0,
    "interest_alignment": 0.05,
}
DIMENSIONS = tuple(DEFAULT_WEIGHTS)
# Dimensions that need semantic understanding; deterministic rules never score them.
SEMANTIC_ONLY = ("architecture_alignment", "leadership_alignment", "domain_alignment")

BLOCKER_SCORE_CAP = 0.2
TECH_MATCHES_FOR_FULL_SCORE = 3

ANNUALIZATION = {"YEAR": 1.0, "MONTH": 12.0, "WEEK": 52.0, "DAY": 260.0, "HOUR": 2080.0}

SENIORITY_LEVELS: dict[str, frozenset[str]] = {
    "entry": frozenset({"entry", "junior", "jr", "associate", "intern"}),
    "mid": frozenset({"mid", "intermediate"}),
    "senior": frozenset({"senior", "sr"}),
    "staff": frozenset({"staff"}),
    "principal": frozenset({"principal"}),
    "lead": frozenset({"lead"}),
    "manager": frozenset({"manager", "management"}),
    "director": frozenset({"director", "vp", "head"}),
    "executive": frozenset({"cto", "ceo", "cfo", "president", "chief"}),
}

_STOP_WORDS = frozenset({"and", "the", "for", "with", "of"})


@dataclass
class Outcome:
    """Result of one rule: a score (None = not scored) plus its findings."""

    score: float | None = None
    strengths: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    transferable: list[str] = field(default_factory=list)


@dataclass
class EvaluationResult:
    overall_score: float
    confidence: float
    dimension_scores: dict[str, float]
    strengths: list[str]
    transferable_matches: list[str]
    gaps: list[str]
    blockers: list[str]
    unknowns: list[str]
    explanation: str
    evaluator_version: str = EVALUATOR_VERSION
    model_provider: str | None = None
    model_name: str | None = None


def normalize_text(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9+#.]+", " ", value.lower()).split())


def tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def contains_term(text: str, term: str) -> bool:
    """Whole-word containment; safe for terms like 'c++', '.net' and 'c#'."""
    term = term.strip().lower()
    if len(term) < 2:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text.lower()) is not None


def name_matches(company: str, candidate: str) -> bool:
    a, b = normalize_text(company), normalize_text(candidate)
    return bool(b) and (a == b or a.startswith(b + " "))


def annualize(amount: float, period: str | None) -> float | None:
    if period is None:
        return None
    factor = ANNUALIZATION.get(period.upper())
    return None if factor is None else amount * factor


class DeterministicEvaluator:
    """Evaluates job-profile fit using deterministic rules."""

    def evaluate(
        self,
        job: Job,
        profile: Profile,
        skill_catalog: list[SkillInfo] | None = None,
    ) -> EvaluationResult:
        prefs = profile.search_preferences
        outcomes: dict[str, Outcome] = {
            "role_alignment": self._role(job, profile.role_families, profile.role_targets),
            "seniority_alignment": self._seniority(job, profile.role_targets),
            "technical_alignment": self._technical(job, profile, skill_catalog or []),
            "location_alignment": self._location_and_remote(job, prefs),
            "compensation_alignment": self._compensation(job, prefs),
            "employment_alignment": self._employment(job, prefs),
            "interest_alignment": self._interest(job, prefs),
        }
        for dim in SEMANTIC_ONLY:
            outcomes[dim] = Outcome(
                unknowns=[f"{dim}: no deterministic signal (needs semantic evaluation)"]
            )

        strengths: list[str] = []
        gaps: list[str] = []
        blockers: list[str] = self._company_industry_blockers(job, prefs)
        unknowns: list[str] = []
        transferable: list[str] = []
        scores: dict[str, float] = {}
        for dim in DIMENSIONS:
            outcome = outcomes[dim]
            strengths += outcome.strengths
            gaps += outcome.gaps
            blockers += outcome.blockers
            unknowns += outcome.unknowns
            transferable += outcome.transferable
            if outcome.score is not None:
                scores[dim] = round(max(0.0, min(1.0, outcome.score)), 4)

        weights = self._weights(profile)
        overall, confidence = self._combine(scores, weights)
        if blockers:
            overall = min(overall, BLOCKER_SCORE_CAP)
        return EvaluationResult(
            overall_score=round(overall, 4),
            confidence=confidence,
            dimension_scores=scores,
            strengths=strengths,
            transferable_matches=transferable,
            gaps=gaps,
            blockers=blockers,
            unknowns=unknowns,
            explanation=self._explain(job, profile, scores, overall, confidence, blockers, gaps),
        )

    # -- scoring ---------------------------------------------------------------------------

    @staticmethod
    def _weights(profile: Profile) -> dict[str, float]:
        custom = profile.scoring_preferences.weights if profile.scoring_preferences else {}
        picked = {d: float(w) for d, w in custom.items() if d in DIMENSIONS and w > 0}
        return picked or {d: w for d, w in DEFAULT_WEIGHTS.items() if w > 0}

    @staticmethod
    def _combine(scores: dict[str, float], weights: dict[str, float]) -> tuple[float, float]:
        """Weighted mean over scored dimensions (weights renormalised); confidence is the
        share of total configured weight that actually had a deterministic signal."""
        total = sum(weights.values())
        scored = {d: w for d, w in weights.items() if d in scores}
        scored_weight = sum(scored.values())
        if scored_weight > 0:
            overall = sum(scores[d] * w for d, w in scored.items()) / scored_weight
            return overall, round(scored_weight / total, 2)
        if scores:  # signals exist only on dimensions the profile gave no weight
            return sum(scores.values()) / len(scores), 0.0
        return 0.0, 0.0

    # -- rules -----------------------------------------------------------------------------

    def _role(self, job: Job, families: list[RoleFamily], targets: list[RoleTarget]) -> Outcome:
        enabled = [f for f in families if f.enabled]
        if not enabled and not targets:
            return Outcome(unknowns=["role_alignment: no role families or targets configured"])
        title = job.title.lower()
        title_words = set(tokens(title))
        best = 0.0
        reason = ""
        for family in enabled:
            name = family.name.lower()
            if contains_term(title, name):
                score = 0.9
            else:
                words = [w for w in tokens(name) if len(w) >= 3 and w not in _STOP_WORDS]
                score = 0.7 * sum(w in title_words for w in words) / len(words) if words else 0.0
            if score > best:
                best, reason = score, f"role family '{family.name}'"
        for target in targets:
            score = self._target_score(title, target)
            if score > best:
                best, reason = score, "a configured role target"
        out = Outcome(score=best)
        if best >= 0.8:
            out.strengths.append(f"Strong role alignment: '{job.title}' matches {reason}")
        elif best >= 0.5:
            out.strengths.append(f"Partial role alignment: '{job.title}' overlaps {reason}")
        else:
            out.gaps.append(f"Weak role alignment: '{job.title}' does not match target roles")
        return out

    @staticmethod
    def _target_score(title: str, target: RoleTarget) -> float:
        score = 0.0
        pattern = (target.title_pattern or "").lower().strip()
        if pattern:
            if "*" in pattern:
                regex = ".*".join(re.escape(part) for part in pattern.split("*"))
                if re.search(regex, title):
                    score = 0.95
            elif contains_term(title, pattern):
                score = 0.9
        include = sum(contains_term(title, k) for k in target.include_keywords)
        score = max(score, min(1.0, include * 0.3))
        exclude = sum(contains_term(title, k) for k in target.exclude_keywords)
        return max(0.0, score - min(0.8, exclude * 0.4))

    @staticmethod
    def _title_levels(title: str) -> set[str]:
        words = set(tokens(title))
        return {level for level, markers in SENIORITY_LEVELS.items() if words & markers}

    def _seniority(self, job: Job, targets: list[RoleTarget]) -> Outcome:
        wanted = {s.lower().replace("-level", "") for t in targets for s in t.target_seniority}
        if not wanted:
            return Outcome(unknowns=["seniority_alignment: no target seniority configured"])
        levels = self._title_levels(job.title)
        if not levels:
            return Outcome(unknowns=[f"seniority_alignment: no level stated in '{job.title}'"])
        if levels & wanted:
            return Outcome(score=1.0, strengths=[f"Seniority matches target: {sorted(levels)}"])
        return Outcome(
            score=0.2,
            gaps=[f"Seniority {sorted(levels)} is outside targets {sorted(wanted)}"],
        )

    def _technical(self, job: Job, profile: Profile, catalog: list[SkillInfo]) -> Outcome:
        if not profile.skills:
            return Outcome(unknowns=["technical_alignment: profile has no skills"])
        text = " ".join([job.title, job.description_text or "", *job.requirement_texts])
        if not text.strip():
            return Outcome(unknowns=["technical_alignment: job has no description text"])
        matched = [s for s in profile.skills if self._skill_in_text(s, text)]
        out = Outcome(score=min(1.0, len(matched) / TECH_MATCHES_FOR_FULL_SCORE))
        if matched:
            out.strengths.append("Skills found in job: " + ", ".join(s.name for s in matched))
        else:
            out.gaps.append("None of the profile's skills appear in the job text")
        out.transferable += self._transferable(text, profile, catalog)
        return out

    @staticmethod
    def _skill_in_text(skill: SkillInfo, text: str) -> bool:
        return any(contains_term(text, term) for term in [skill.name, *skill.aliases])

    def _transferable(self, text: str, profile: Profile, catalog: list[SkillInfo]) -> list[str]:
        held = {s.name.lower() for s in profile.skills}
        held |= {a.lower() for s in profile.skills for a in s.aliases}
        by_category: dict[str, str] = {}
        for skill in profile.skills:
            if skill.category:
                by_category.setdefault(skill.category.lower(), skill.name)
        found: list[str] = []
        for skill in catalog:
            if skill.name.lower() in held or not skill.category:
                continue
            related = by_category.get(skill.category.lower())
            if related and self._skill_in_text(skill, text):
                found.append(
                    f"{skill.name} (not listed; related to your {related}, "
                    f"same category '{skill.category}')"
                )
        return found

    def _location_and_remote(self, job: Job, prefs: SearchPreferences | None) -> Outcome:
        if prefs is None:
            return Outcome()
        loc = self._location(job, prefs)
        rem = self._remote(job, prefs)
        scored = [o.score for o in (loc, rem) if o.score is not None]
        return Outcome(
            score=sum(scored) / len(scored) if scored else None,
            strengths=loc.strengths + rem.strengths,
            gaps=loc.gaps + rem.gaps,
            blockers=loc.blockers + rem.blockers,
            unknowns=loc.unknowns + rem.unknowns,
        )

    @staticmethod
    def _location(job: Job, prefs: SearchPreferences) -> Outcome:
        terms = [*prefs.allowed_countries, *prefs.allowed_regions, *prefs.allowed_cities]
        if not terms or (job.remote_type or "").upper() == "REMOTE":
            return Outcome()
        if not job.location_text:
            return Outcome(unknowns=["location_alignment: job has no location"])
        if any(contains_term(job.location_text, t) for t in terms):
            return Outcome(score=1.0, strengths=[f"Location allowed: {job.location_text}"])
        if prefs.relocation_allowed:
            return Outcome(score=0.6, gaps=[f"Would require relocation to {job.location_text}"])
        return Outcome(
            score=0.0,
            blockers=[f"Location '{job.location_text}' is outside allowed locations"],
        )

    @staticmethod
    def _remote(job: Job, prefs: SearchPreferences) -> Outcome:
        policy = (prefs.remote_preference or "NEUTRAL").upper()
        if policy == "NEUTRAL":
            return Outcome()
        kind = (job.remote_type or "").upper()
        if kind not in {"REMOTE", "HYBRID", "ONSITE"}:
            return Outcome(unknowns=["location_alignment: job remote type unknown"])
        table: dict[str, dict[str, float | None]] = {
            "REQUIRED": {"REMOTE": 1.0, "HYBRID": None, "ONSITE": None},
            "PREFERRED": {"REMOTE": 1.0, "HYBRID": 0.6, "ONSITE": 0.3},
            "AVOID": {"REMOTE": 0.2, "HYBRID": 0.6, "ONSITE": 1.0},
            "BLOCK": {"REMOTE": None, "HYBRID": 0.6, "ONSITE": 1.0},
        }
        if policy not in table:
            return Outcome(unknowns=[f"location_alignment: unknown remote policy {policy}"])
        score = table[policy][kind]
        if score is None:
            message = (
                f"Remote work required but job is {kind}"
                if policy == "REQUIRED"
                else "Remote work is blocked by the profile but job is REMOTE"
            )
            return Outcome(score=0.0, blockers=[message])
        out = Outcome(score=score)
        if score >= 0.8:
            out.strengths.append(f"Work arrangement fits ({policy.lower()} / {kind})")
        elif score < 0.5:
            out.gaps.append(f"Work arrangement {kind} is disfavoured ({policy.lower()})")
        return out

    @staticmethod
    def _compensation(job: Job, prefs: SearchPreferences | None) -> Outcome:
        if prefs is None:
            return Outcome()
        minimum = prefs.minimum_base_salary or prefs.minimum_total_comp
        if not minimum:
            return Outcome()
        figures = [v for v in (job.salary_min, job.salary_max) if v is not None]
        if not figures:
            return Outcome(unknowns=["compensation_alignment: job lists no salary"])
        if prefs.currency and job.salary_currency and prefs.currency != job.salary_currency:
            return Outcome(
                unknowns=[
                    f"compensation_alignment: currency mismatch "
                    f"({job.salary_currency} vs {prefs.currency}); not converted"
                ]
            )
        low = annualize(min(figures), job.salary_period)
        high = annualize(max(figures), job.salary_period)
        if low is None or high is None:
            return Outcome(unknowns=["compensation_alignment: salary period unknown"])
        label = f"{job.salary_currency or ''} {low:,.0f}-{high:,.0f}/yr".strip()
        if high < minimum:
            return Outcome(
                score=0.0,
                blockers=[f"Salary {label} is below minimum {minimum:,.0f}/yr"],
            )
        if low >= minimum:
            score = min(1.0, 0.6 + 0.4 * (low - minimum) / minimum)
            return Outcome(score=score, strengths=[f"Salary {label} meets minimum {minimum:,.0f}"])
        return Outcome(
            score=0.5,
            gaps=[f"Salary range {label} straddles minimum {minimum:,.0f}/yr"],
        )

    @staticmethod
    def _employment(job: Job, prefs: SearchPreferences | None) -> Outcome:
        if prefs is None or not prefs.employment_types:
            return Outcome()
        if not job.employment_type:
            return Outcome(unknowns=["employment_alignment: job employment type unknown"])
        allowed = {t.upper() for t in prefs.employment_types}
        if job.employment_type.upper() in allowed:
            return Outcome(score=1.0, strengths=[f"Employment type: {job.employment_type}"])
        return Outcome(
            score=0.0,
            blockers=[f"Employment type {job.employment_type} is not in {sorted(allowed)}"],
        )

    @staticmethod
    def _company_industry_blockers(job: Job, prefs: SearchPreferences | None) -> list[str]:
        if prefs is None:
            return []
        found: list[str] = []
        if any(name_matches(job.company, c) for c in prefs.excluded_companies):
            found.append(f"Company '{job.company}' is excluded")
        if job.industry and any(
            normalize_text(job.industry) == normalize_text(i) for i in prefs.excluded_industries
        ):
            found.append(f"Industry '{job.industry}' is excluded")
        return found

    @staticmethod
    def _interest(job: Job, prefs: SearchPreferences | None) -> Outcome:
        if prefs is None:
            return Outcome()
        out = Outcome()
        if any(name_matches(job.company, c) for c in prefs.preferred_companies):
            out.score = 1.0
            out.strengths.append(f"Preferred company: {job.company}")
        if job.industry and any(
            normalize_text(job.industry) == normalize_text(i) for i in prefs.preferred_industries
        ):
            out.score = 1.0
            out.strengths.append(f"Preferred industry: {job.industry}")
        return out

    # -- explanation -----------------------------------------------------------------------

    @staticmethod
    def _explain(
        job: Job,
        profile: Profile,
        scores: dict[str, float],
        overall: float,
        confidence: float,
        blockers: list[str],
        gaps: list[str],
    ) -> str:
        parts = [
            f"'{job.title}' at {job.company} for profile '{profile.display_name}': "
            f"{overall:.0%} fit from {len(scores)} scored dimension(s), "
            f"confidence {confidence:.0%}."
        ]
        if blockers:
            parts.append(
                f"Blocked ({'; '.join(blockers)}); score capped at {BLOCKER_SCORE_CAP:.0%}."
            )
        if gaps:
            parts.append("Gaps: " + "; ".join(gaps[:3]) + ".")
        parts.append("Deterministic rules only; dimensions without a signal are listed as unknown.")
        return " ".join(parts)


def create_deterministic_evaluator() -> DeterministicEvaluator:
    return DeterministicEvaluator()
