from types import SimpleNamespace

from careerflow.application.evaluations.mapping import (
    to_job,
    to_profile,
    to_role_families,
    to_scoring_preferences,
    to_search_preferences,
)


def test_to_job_copies_domain_fields_and_ignores_orm_extras() -> None:
    orm = SimpleNamespace(title="Engineer", company="Acme", description_text="Build", id="x", remote_type=None)
    job = to_job(orm)
    assert (job.title, job.company, job.description_text, job.remote_type) == ("Engineer", "Acme", "Build", None)


def test_missing_preferences_map_to_none() -> None:
    assert to_search_preferences(None) is None
    assert to_scoring_preferences(None) is None


def test_orm_none_values_fall_back_to_domain_defaults() -> None:
    prefs = to_search_preferences(SimpleNamespace(remote_preference="REMOTE", allowed_countries=None))
    assert prefs is not None
    assert prefs.remote_preference == "REMOTE"
    assert prefs.allowed_countries == []


def test_to_profile_embeds_mapped_children() -> None:
    families = to_role_families([SimpleNamespace(name="Backend", priority=1, enabled=True)])
    profile = to_profile(SimpleNamespace(display_name="Jordan Lee"), families, [], None, None)
    assert profile.display_name == "Jordan Lee"
    assert [f.name for f in profile.role_families] == ["Backend"]
