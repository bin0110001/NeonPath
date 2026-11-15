import ast
from pathlib import Path

from careerflow.domain.evaluations import service as evaluator_module
from careerflow.domain.evaluations.service import (
    EVALUATOR_VERSION,
    DeterministicEvaluator,
    annualize,
    contains_term,
)
from careerflow.domain.jobs.model import Job
from careerflow.domain.profiles.model import (
    Profile,
    RoleFamily,
    RoleTarget,
    ScoringPreferences,
    SearchPreferences,
    SkillInfo,
)

evaluator = DeterministicEvaluator()


def make_job(**overrides: object) -> Job:
    values: dict[str, object] = {
        "title": "Principal AI Engineer",
        "company": "Acme Labs",
        "description_text": "Build LLM applications in Python on Azure.",
        "location_text": "Austin, Texas, United States",
        "remote_type": "REMOTE",
        "employment_type": "FULL_TIME",
        "salary_min": 180000,
        "salary_max": 220000,
        "salary_currency": "USD",
        "salary_period": "YEAR",
    }
    values.update(overrides)
    return Job(**values)  # type: ignore[arg-type]


def jordan() -> Profile:
    return Profile(
        display_name="Jordan",
        skills=[SkillInfo("Python", category="language"), SkillInfo("LLM", ["Large Language Models"])],
        role_families=[RoleFamily("AI Engineer")],
        role_targets=[RoleTarget(title_pattern="principal*engineer", target_seniority=["principal"])],
        search_preferences=SearchPreferences(
            remote_preference="REQUIRED", minimum_base_salary=170000, currency="USD"
        ),
    )


def morgan() -> Profile:
    return Profile(
        display_name="Morgan",
        skills=[SkillInfo("Python", category="language"), SkillInfo("SQL")],
        role_families=[RoleFamily("Data Scientist")],
        role_targets=[RoleTarget(title_pattern="data scientist", target_seniority=["senior"])],
        search_preferences=SearchPreferences(remote_preference="PREFERRED"),
    )


def test_no_dimension_is_fabricated() -> None:
    result = evaluator.evaluate(make_job(), jordan())
    for dim in ("architecture_alignment", "leadership_alignment", "domain_alignment"):
        assert dim not in result.dimension_scores
        assert any(u.startswith(dim) for u in result.unknowns)
    assert result.evaluator_version == EVALUATOR_VERSION == "deterministic-v2.0"


def test_same_job_differs_per_profile() -> None:
    job = make_job()
    a, b = evaluator.evaluate(job, jordan()), evaluator.evaluate(job, morgan())
    assert a.overall_score > b.overall_score
    assert a.dimension_scores["role_alignment"] > b.dimension_scores["role_alignment"]
    assert a.dimension_scores["seniority_alignment"] == 1.0
    assert b.dimension_scores["seniority_alignment"] == 0.2


def test_remote_required_onsite_is_blocker() -> None:
    result = evaluator.evaluate(make_job(remote_type="ONSITE"), jordan())
    assert any("Remote work required" in b for b in result.blockers)
    assert result.overall_score <= 0.2


def test_remote_block_policy_blocks_remote_jobs() -> None:
    profile = jordan()
    profile.search_preferences = SearchPreferences(remote_preference="BLOCK")
    assert evaluator.evaluate(make_job(), profile).blockers


def test_salary_below_minimum_after_annualization() -> None:
    job = make_job(salary_min=10000, salary_max=12000, salary_period="MONTH")  # 120k-144k/yr
    result = evaluator.evaluate(job, jordan())
    assert any("below minimum" in b for b in result.blockers)


def test_salary_hourly_meets_minimum() -> None:
    job = make_job(salary_min=100, salary_max=120, salary_period="HOUR")  # 208k-249.6k/yr
    result = evaluator.evaluate(job, jordan())
    assert not result.blockers
    assert result.dimension_scores["compensation_alignment"] > 0.6


def test_currency_mismatch_is_unknown_not_converted() -> None:
    result = evaluator.evaluate(make_job(salary_currency="EUR"), jordan())
    assert "compensation_alignment" not in result.dimension_scores
    assert any("currency mismatch" in u for u in result.unknowns)
    assert not result.blockers


def test_annualize() -> None:
    assert annualize(10, "HOUR") == 20800
    assert annualize(5, "WEEKLY") is None
    assert annualize(5, None) is None


def test_excluded_company_and_industry_block() -> None:
    profile = jordan()
    assert profile.search_preferences is not None
    profile.search_preferences.excluded_companies = ["acme labs"]
    assert any("excluded" in b for b in evaluator.evaluate(make_job(), profile).blockers)
    profile.search_preferences.excluded_companies = []
    profile.search_preferences.excluded_industries = ["Tobacco"]
    job = make_job(industry="tobacco")
    assert any("Industry" in b for b in evaluator.evaluate(job, profile).blockers)


def test_company_exclusion_requires_whole_name() -> None:
    profile = jordan()
    assert profile.search_preferences is not None
    profile.search_preferences.excluded_companies = ["Acme"]
    assert evaluator.evaluate(make_job(company="Acme Labs"), profile).blockers
    assert not evaluator.evaluate(make_job(company="Acmeville"), profile).blockers


def test_preferred_company_scores_interest() -> None:
    profile = jordan()
    assert profile.search_preferences is not None
    profile.search_preferences.preferred_companies = ["Acme Labs"]
    result = evaluator.evaluate(make_job(), profile)
    assert result.dimension_scores["interest_alignment"] == 1.0


def test_location_rules() -> None:
    profile = Profile("P", search_preferences=SearchPreferences(allowed_cities=["Austin"]))
    onsite = make_job(remote_type="ONSITE")
    assert evaluator.evaluate(onsite, profile).dimension_scores["location_alignment"] == 1.0
    far = make_job(remote_type="ONSITE", location_text="Berlin, Germany")
    assert evaluator.evaluate(far, profile).blockers
    profile.search_preferences = SearchPreferences(allowed_cities=["Austin"], relocation_allowed=True)
    result = evaluator.evaluate(far, profile)
    assert not result.blockers
    assert result.dimension_scores["location_alignment"] == 0.6


def test_employment_type_blocker() -> None:
    profile = Profile("P", search_preferences=SearchPreferences(employment_types=["FULL_TIME"]))
    assert evaluator.evaluate(make_job(employment_type="CONTRACT"), profile).blockers
    ok = evaluator.evaluate(make_job(employment_type="full_time"), profile)
    assert ok.dimension_scores["employment_alignment"] == 1.0


def test_skill_matching_uses_aliases_and_word_boundaries() -> None:
    assert contains_term("We use C++ and .NET", "c++")
    assert contains_term("We use C++ and .NET", ".net")
    assert not contains_term("pythonic style", "python")
    job = make_job(description_text="Experience with Large Language Models required")
    result = evaluator.evaluate(job, jordan())
    assert any("LLM" in s for s in result.strengths)


def test_transferable_match_via_shared_category() -> None:
    profile = Profile("P", skills=[SkillInfo("Azure ML", category="cloud-ml")])
    catalog = [SkillInfo("Azure ML", category="cloud-ml"), SkillInfo("SageMaker", category="cloud-ml")]
    job = make_job(description_text="Deploy models on SageMaker")
    result = evaluator.evaluate(job, profile, catalog)
    assert len(result.transferable_matches) == 1
    assert "SageMaker" in result.transferable_matches[0]


def test_profile_weights_normalised_over_scored_dimensions() -> None:
    profile = jordan()
    profile.scoring_preferences = ScoringPreferences(
        {"role_alignment": 1.0, "architecture_alignment": 1.0}
    )
    result = evaluator.evaluate(make_job(), profile)
    # architecture is unscored, so overall equals the role score; half the weight was unscored.
    assert result.overall_score == result.dimension_scores["role_alignment"]
    assert result.confidence == 0.5


def test_empty_profile_yields_zero_confidence() -> None:
    result = evaluator.evaluate(make_job(), Profile("Blank"))
    assert result.dimension_scores == {}
    assert result.overall_score == 0.0
    assert result.confidence == 0.0
    assert len(result.unknowns) >= 3


def test_domain_module_has_no_framework_imports() -> None:
    tree = ast.parse(Path(evaluator_module.__file__ or "").read_text(encoding="utf-8"))
    imported = {
        n.module.split(".")[0] if isinstance(n, ast.ImportFrom) and n.module else a.name.split(".")[0]
        for n in ast.walk(tree)
        if isinstance(n, ast.Import | ast.ImportFrom)
        for a in (n.names if isinstance(n, ast.Import) else [n])
    }
    assert not imported & {"fastapi", "sqlalchemy", "pydantic"}
