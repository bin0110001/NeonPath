"""Evidence-backed claims and the merge of semantic findings into a deterministic result.

Rules (ADR-009, ADR-011):
* A *positive* claim (strength / transferable) is only ``evidence`` if every cited id
  resolves to a real profile record; otherwise it is downgraded to ``unverified``.
* The model may label a claim ``inference``; that marker is kept and shown to users.
* Deterministic blockers always win: the semantic layer can add gaps/unknowns and fill
  dimensions that rules cannot score, but never removes or overrides a blocker.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from careerflow.domain.evaluations.service import (
    BLOCKER_SCORE_CAP,
    SEMANTIC_ONLY,
    DeterministicEvaluator,
    EvaluationResult,
)
from careerflow.domain.profiles.model import Profile

POSITIVE_KINDS = frozenset({"strength", "transferable"})
BASES = frozenset({"evidence", "inference", "unverified"})


@dataclass(frozen=True)
class Claim:
    text: str
    kind: str  # strength | transferable | gap
    basis: str  # evidence | inference | unverified
    evidence_ids: tuple[str, ...] = ()
    note: str | None = None  # why a claim was downgraded


def validate_claims(claims: list[Claim], known_evidence_ids: set[str]) -> list[Claim]:
    """Return claims whose ``basis`` is trustworthy given what the profile really contains."""
    checked: list[Claim] = []
    for claim in claims:
        basis = claim.basis if claim.basis in BASES else "unverified"
        ids = tuple(dict.fromkeys(claim.evidence_ids))
        valid = tuple(i for i in ids if i in known_evidence_ids)
        note = claim.note
        if claim.kind in POSITIVE_KINDS:
            if basis == "evidence":
                if not ids:
                    basis, note = "unverified", "no evidence cited"
                elif len(valid) != len(ids):
                    basis, note = "unverified", "cited evidence does not exist in the profile"
                    valid = ()
            # an "inference" may cite supporting records but needs none
        checked.append(replace(claim, basis=basis, evidence_ids=valid, note=note))
    return checked


@dataclass
class SemanticFindings:
    claims: list[Claim] = field(default_factory=list)
    dimension_scores: dict[str, float] = field(default_factory=dict)
    explanation: str = ""


def merge_semantic(
    deterministic: EvaluationResult,
    findings: SemanticFindings,
    profile: Profile,
    evaluator: DeterministicEvaluator,
    version: str,
) -> EvaluationResult:
    scores = dict(deterministic.dimension_scores)
    unknowns = list(deterministic.unknowns)
    for dim, value in findings.dimension_scores.items():
        if dim in SEMANTIC_ONLY:  # the model may only score what rules cannot
            scores[dim] = round(max(0.0, min(1.0, value)), 4)
            unknowns = [u for u in unknowns if not u.startswith(dim)]

    strengths = list(deterministic.strengths)
    transferable = list(deterministic.transferable_matches)
    gaps = list(deterministic.gaps)
    for claim in findings.claims:
        label = _label(claim)
        if claim.kind == "strength":
            strengths.append(label)
        elif claim.kind == "transferable":
            transferable.append(label)
        elif claim.kind == "gap":
            gaps.append(label)

    overall, confidence = evaluator.combine(scores, profile)
    if deterministic.blockers:
        overall = min(overall, BLOCKER_SCORE_CAP)  # blockers always win
    explanation = deterministic.explanation
    if findings.explanation:
        explanation = f"{explanation} Semantic assessment: {findings.explanation}"
    return replace(
        deterministic,
        overall_score=round(overall, 4),
        confidence=confidence,
        dimension_scores=scores,
        strengths=strengths,
        transferable_matches=transferable,
        gaps=gaps,
        unknowns=unknowns,
        explanation=explanation,
        evaluator_version=version,
    )


def _label(claim: Claim) -> str:
    if claim.basis == "evidence":
        return f"{claim.text} [evidence: {', '.join(claim.evidence_ids)}]"
    return f"{claim.text} [{claim.basis}]"
