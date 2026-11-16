"""Deterministic interview preparation (plan section 15). Pure logic.

Built from the job text and the profile's own records; works with AI disabled. Suggestions
that point at the candidate's experience always name the record they come from.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from careerflow.domain.applications.tailoring import (
    AchievementFact,
    JobFacts,
    SkillFact,
    recommend,
)
from careerflow.domain.evaluations.service import contains_term

PREP_VERSION = "interview-prep-v1"

ARCHITECTURE_CUES: dict[str, str] = {
    "distributed": "Distributed systems: consistency, partitioning, failure modes",
    "scal": "Scaling: load, caching, back-pressure, capacity planning",
    "latency": "Latency budgets and performance trade-offs",
    "microservice": "Service boundaries and inter-service communication",
    "event": "Event-driven design: queues, ordering, idempotency",
    "streaming": "Streaming pipelines and exactly-once semantics",
    "kubernetes": "Container orchestration and deployment strategies",
    "multi-tenant": "Multi-tenancy, isolation and noisy-neighbour control",
    "security": "Security architecture: authN/authZ, secrets, threat modelling",
    "observab": "Observability: metrics, tracing, alerting, SLOs",
    "data pipeline": "Data pipeline design: ingestion, quality, lineage",
}
ML_CUES: dict[str, str] = {
    "llm": "LLM application design: prompting, grounding, evaluation, cost and latency",
    "rag": "Retrieval-augmented generation: chunking, embeddings, ranking",
    "fine-tun": "Fine-tuning vs prompting trade-offs",
    "mlops": "MLOps: deployment, monitoring, drift, retraining",
    "embedding": "Embeddings and vector search",
    "forecast": "Forecasting methods and backtesting",
    "experiment": "Experiment design, power and pitfalls",
    "feature": "Feature engineering and leakage",
    "evaluation": "Model evaluation, metrics and error analysis",
    "machine learning": "Core machine-learning fundamentals and model selection",
}
TYPE_FOCUS: dict[str, list[str]] = {
    "recruiter": ["Motivation for the role", "Compensation and logistics expectations", "A two-minute career summary"],
    "hiring_manager": ["Scope of the role and first 90 days", "How you work with stakeholders", "Biggest relevant results"],
    "coding": ["Data structures and algorithms fundamentals", "Writing clear, tested code under time pressure", "Talking through trade-offs aloud"],
    "system_design": ["Requirements, constraints and capacity estimates", "High-level architecture and data model", "Failure modes and trade-offs"],
    "architecture": ["Architectural decision records and trade-offs", "Evolving a system under change", "Cross-team technical influence"],
    "machine_learning": ["Problem framing and metrics", "Data quality and leakage", "Deploying and monitoring models"],
    "behavioral": ["STAR stories with measurable results", "Conflict, failure and learning", "Leadership without authority"],
    "panel": ["Consistent narrative across interviewers", "Addressing each panelist's concerns"],
    "executive": ["Business impact and strategy", "Risk, cost and prioritisation"],
    "other": ["Role fit and motivation"],
}
BASE_QUESTIONS = [
    "What does success look like in the first six months?",
    "How is the team structured, and who does this role work with most?",
    "What are the biggest technical or organisational challenges right now?",
    "How are decisions made and how is performance evaluated?",
]
LEADERSHIP_TAGS = ("leadership", "mentoring", "management", "stakeholder", "conflict", "ownership")


@dataclass(frozen=True)
class AchievementRef:
    id: str
    title: str
    why: str


@dataclass
class InterviewPrep:
    interview_type: str
    focus_areas: list[str] = field(default_factory=list)
    relevant_achievements: list[AchievementRef] = field(default_factory=list)
    technical_topics: list[str] = field(default_factory=list)
    system_design_themes: list[str] = field(default_factory=list)
    ai_ml_topics: list[str] = field(default_factory=list)
    leadership_stories: list[AchievementRef] = field(default_factory=list)
    weak_spots: list[str] = field(default_factory=list)
    questions_to_ask: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _cues(table: dict[str, str], text: str) -> list[str]:
    return [label for cue, label in table.items() if cue in text.lower()]


def prepare(
    interview_type: str,
    job: JobFacts,
    company: str,
    skills: list[SkillFact],
    achievements: list[AchievementFact],
    known_skill_names: list[str] | None = None,
) -> InterviewPrep:
    text = f"{job.title}\n{job.description}\n" + "\n".join([*job.required_skills, *job.preferred_skills])
    rec = recommend(job, skills, achievements, [], known_skill_names)
    by_id = {a.id: a for a in achievements}
    prep = InterviewPrep(interview_type=interview_type)

    prep.focus_areas = list(TYPE_FOCUS.get(interview_type, TYPE_FOCUS["other"]))
    for a_id in rec.achievement_ids:
        a = by_id[a_id]
        prep.relevant_achievements.append(AchievementRef(a.id, a.title, "matches the job's requirements"))
        if not a.verified:
            prep.warnings.append(f"Achievement '{a.title}' is not marked verified; be ready to substantiate it.")

    wanted = [s for s in [*job.required_skills, *job.preferred_skills] if s]
    held = [s.name for s in skills if any(contains_term(text, t) for t in (s.name, *s.aliases))]
    prep.technical_topics = list(dict.fromkeys([*wanted, *held]))[:12]
    prep.system_design_themes = _cues(ARCHITECTURE_CUES, text)
    prep.ai_ml_topics = _cues(ML_CUES, text)

    stories = [a for a in achievements if any(t.lower() in LEADERSHIP_TAGS for t in a.tags)]
    for a in stories[:3]:
        prep.leadership_stories.append(AchievementRef(a.id, a.title, "tagged: " + ", ".join(a.tags[:3])))

    prep.weak_spots = list(rec.missing_evidence)
    prep.questions_to_ask = [
        *BASE_QUESTIONS,
        f"What would make someone in the {job.title} role stand out at {company}?",
    ]
    if prep.system_design_themes:
        prep.questions_to_ask.append("What does the current architecture look like, and where does it hurt most?")
    if prep.ai_ml_topics:
        prep.questions_to_ask.append("How are models or AI features evaluated and monitored in production today?")
    return prep
