"""Map ORM rows to the domain dataclasses the deterministic evaluator consumes.

The domain layer must not depend on ORM entities, so the application layer copies the
fields each domain dataclass declares from the matching ORM attributes.
"""

from collections.abc import Iterable
from dataclasses import MISSING, fields
from typing import Any

from careerflow.domain.jobs.model import Job
from careerflow.domain.profiles.model import (
    Profile,
    RoleFamily,
    RoleTarget,
    ScoringPreferences,
    SearchPreferences,
)


def _copy_fields[T](cls: type[T], source: object, **overrides: Any) -> T:
    values: dict[str, Any] = {}
    for f in fields(cls):  # type: ignore[arg-type]
        if f.name in overrides:
            values[f.name] = overrides[f.name]
        elif hasattr(source, f.name):
            value = getattr(source, f.name)
            if value is not None or f.default is None:
                values[f.name] = value
        elif f.default is MISSING and f.default_factory is MISSING:
            raise ValueError(f"{cls.__name__}.{f.name} has no counterpart on {type(source).__name__}")
    return cls(**values)


def to_job(job: object) -> Job:
    return _copy_fields(Job, job)


def to_search_preferences(prefs: object | None) -> SearchPreferences | None:
    return None if prefs is None else _copy_fields(SearchPreferences, prefs)


def to_scoring_preferences(prefs: object | None) -> ScoringPreferences | None:
    return None if prefs is None else _copy_fields(ScoringPreferences, prefs)


def to_role_families(rows: Iterable[object]) -> list[RoleFamily]:
    return [_copy_fields(RoleFamily, row) for row in rows]


def to_role_targets(rows: Iterable[object]) -> list[RoleTarget]:
    return [_copy_fields(RoleTarget, row) for row in rows]


def to_profile(
    profile: object,
    role_families: list[RoleFamily],
    role_targets: list[RoleTarget],
    search_preferences: SearchPreferences | None,
    scoring_preferences: ScoringPreferences | None,
) -> Profile:
    return _copy_fields(
        Profile,
        profile,
        role_families=role_families,
        role_targets=role_targets,
        search_preferences=search_preferences,
        scoring_preferences=scoring_preferences,
        skills=[],
    )
