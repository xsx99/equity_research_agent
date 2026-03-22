"""Prompt registry — versioned prompt management."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import ClassVar

# Default location for .txt prompt templates bundled with this package
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


@dataclass(frozen=True)
class Prompt:
    """
    Immutable descriptor for a versioned prompt template.

    Attributes:
        id:          Logical name, e.g. ``"research"``.
        version:     Version string, e.g. ``"v1"``.
        template:    Raw prompt text (may contain ``$variable`` placeholders).
        description: Optional human-readable description of the prompt.
    """

    id: str
    version: str
    template: str
    description: str = ""

    @property
    def versioned_id(self) -> str:
        """Return ``"{id}_{version}"``, e.g. ``"research_v1"``."""
        return f"{self.id}_{self.version}"

    def render(self, **kwargs) -> str:
        """Return the template with ``$key`` placeholders substituted."""
        return Template(self.template).safe_substitute(**kwargs)


class PromptRegistry:
    """
    Registry that maps ``(id, version)`` pairs to :class:`Prompt` objects.

    Templates are loaded lazily from ``src/prompts/templates/`` the first time
    they are requested and then cached in memory.

    Use :meth:`get_default` to access the module-level singleton, or create an
    isolated instance (e.g. in tests) by calling ``PromptRegistry()`` directly.

    Example::

        registry = PromptRegistry.get_default()
        prompt = registry.get("research", "v1")
        text = prompt.render(ticker="AAPL")
    """

    _instance: ClassVar[PromptRegistry | None] = None

    def __init__(self, templates_dir: Path = TEMPLATES_DIR) -> None:
        self._templates_dir = templates_dir
        # Cache keyed by versioned_id, e.g. "research_v1"
        self._cache: dict[str, Prompt] = {}

    @classmethod
    def get_default(cls) -> "PromptRegistry":
        """Return the module-level singleton, creating it on first call."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get(self, prompt_id: str, version: str) -> Prompt:
        """
        Return the :class:`Prompt` for ``(prompt_id, version)``.

        The template file is loaded from disk on first access using the naming
        convention ``{prompt_id}_{version}.txt``.

        Raises :exc:`FileNotFoundError` if the template file does not exist.
        """
        versioned_id = f"{prompt_id}_{version}"
        if versioned_id not in self._cache:
            filename = f"{versioned_id}.txt"
            path = self._templates_dir / filename
            if not path.exists():
                raise FileNotFoundError(
                    f"Prompt template not found: {path}\n"
                    f"Expected '{filename}' in {self._templates_dir}"
                )
            self._cache[versioned_id] = Prompt(
                id=prompt_id,
                version=version,
                template=path.read_text(encoding="utf-8"),
            )
        return self._cache[versioned_id]

    def register(self, prompt: Prompt) -> None:
        """Manually register a :class:`Prompt` (useful for tests with in-memory templates)."""
        self._cache[prompt.versioned_id] = prompt

    def list_loaded(self) -> list[str]:
        """Return versioned IDs of all currently cached prompts."""
        return list(self._cache.keys())
