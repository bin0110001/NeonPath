"""Versioned prompt registry. Prompt text lives in files, never in domain services.

Layout: ``prompts/<key>/v<N>/system.txt`` and ``user.txt``. Templates use ``$name``
placeholders (``string.Template``) so JSON braces in prompts need no escaping.
``$schema`` is always available and holds the expected response JSON Schema.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from string import Template

DEFAULT_ROOT = Path(__file__).parent / "prompts"
_VERSION_DIR = re.compile(r"^v(\d+)$")


class PromptNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class PromptDefinition:
    key: str
    version: str  # e.g. "v1"
    system: str
    user_template: str

    @property
    def variables(self) -> set[str]:
        return {m.group("named") for m in Template.pattern.finditer(self.user_template) if m.group("named")}

    def render(self, variables: dict[str, str]) -> tuple[str, str]:
        """Return (system, user). Missing variables raise KeyError rather than render blanks."""
        return self.system, Template(self.user_template).substitute(variables)


class PromptRegistry:
    def __init__(self, root: Path = DEFAULT_ROOT) -> None:
        self.root = root

    def versions(self, key: str) -> list[int]:
        directory = self.root / key
        if not directory.is_dir():
            return []
        found = [int(m.group(1)) for p in directory.iterdir() if p.is_dir() and (m := _VERSION_DIR.match(p.name))]
        return sorted(found)

    def get(self, key: str, version: str | None = None) -> PromptDefinition:
        """Fetch a prompt; without ``version`` the highest version wins."""
        if not re.fullmatch(r"[a-z0-9_]+", key):
            raise PromptNotFoundError(f"invalid prompt key: {key!r}")
        if version is None:
            versions = self.versions(key)
            if not versions:
                raise PromptNotFoundError(key)
            version = f"v{versions[-1]}"
        directory = self.root / key / version
        system_file, user_file = directory / "system.txt", directory / "user.txt"
        if not (system_file.is_file() and user_file.is_file()):
            raise PromptNotFoundError(f"{key}/{version}")
        return PromptDefinition(
            key=key,
            version=version,
            system=system_file.read_text(encoding="utf-8").strip(),
            user_template=user_file.read_text(encoding="utf-8").strip(),
        )
