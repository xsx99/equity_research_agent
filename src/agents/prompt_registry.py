"""Versioned prompt registry for trading-agent prompt telemetry."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import yaml
from jinja2 import Environment, StrictUndefined


PROMPTS_ROOT = Path(__file__).resolve().parent / "prompts"


@dataclass(frozen=True)
class PromptTemplate:
    """Versioned prompt template plus persistence metadata."""

    prompt_id: str
    prompt_version: str
    pipeline_name: str
    output_schema_id: str
    output_schema_version: str
    template: str
    template_path: str
    template_hash: str


@dataclass(frozen=True)
class RenderedPrompt:
    """Rendered prompt text plus hash and source-template metadata."""

    text: str
    rendered_prompt_hash: str
    template: PromptTemplate


class PromptRegistry:
    """Load and render versioned prompt YAML files from a controlled root."""

    _instance: ClassVar[PromptRegistry | None] = None

    REQUIRED_FIELDS = (
        "prompt_id",
        "prompt_version",
        "pipeline_name",
        "output_schema_id",
        "output_schema_version",
        "template",
    )

    def __init__(self, root: Path = PROMPTS_ROOT) -> None:
        self.root = Path(root)
        self._cache: dict[tuple[str, str], PromptTemplate] = {}
        self._jinja = Environment(
            autoescape=False,
            keep_trailing_newline=True,
            trim_blocks=False,
            lstrip_blocks=False,
            undefined=StrictUndefined,
        )

    @classmethod
    def get_default(cls) -> "PromptRegistry":
        """Return the module-level singleton registry rooted at agents prompts."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load(self, prompt_id: str, prompt_version: str) -> PromptTemplate:
        """Load a versioned prompt template from disk."""
        key = (prompt_id, prompt_version)
        if key not in self._cache:
            path = self._find_prompt_path(prompt_id, prompt_version)
            self._cache[key] = self._load_prompt_file(path, prompt_id, prompt_version)
        return self._cache[key]

    def render(
        self,
        prompt_id: str,
        prompt_version: str,
        context: dict[str, Any],
    ) -> RenderedPrompt:
        """Render a prompt deterministically and include the rendered hash."""
        prompt_template = self.load(prompt_id, prompt_version)
        rendered_text = self._jinja.from_string(prompt_template.template).render(**context)
        return RenderedPrompt(
            text=rendered_text,
            rendered_prompt_hash=_sha256(rendered_text),
            template=prompt_template,
        )

    def _find_prompt_path(self, prompt_id: str, prompt_version: str) -> Path:
        filename = f"{prompt_id}_{prompt_version}.yaml"
        matches = sorted(path for path in self.root.rglob(filename) if path.is_file())
        if not matches:
            raise FileNotFoundError(
                f"Prompt definition not found: {filename} under {self.root}"
            )
        if len(matches) > 1:
            raise ValueError(f"Multiple prompt definitions found for {filename}: {matches}")
        return matches[0]

    def _load_prompt_file(
        self,
        path: Path,
        expected_prompt_id: str,
        expected_prompt_version: str,
    ) -> PromptTemplate:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"Prompt definition must be a mapping: {path}")

        missing = [field for field in self.REQUIRED_FIELDS if field not in raw]
        if missing:
            raise ValueError(f"Prompt definition missing required fields {missing}: {path}")

        metadata = {field: raw[field] for field in self.REQUIRED_FIELDS}
        for field, value in metadata.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Prompt field must be a non-empty string: {field} in {path}")

        if metadata["prompt_id"] != expected_prompt_id:
            raise ValueError(
                f"Prompt id mismatch in {path}: expected '{expected_prompt_id}', "
                f"got '{metadata['prompt_id']}'"
            )
        if metadata["prompt_version"] != expected_prompt_version:
            raise ValueError(
                f"Prompt version mismatch in {path}: expected '{expected_prompt_version}', "
                f"got '{metadata['prompt_version']}'"
            )

        return PromptTemplate(
            prompt_id=metadata["prompt_id"],
            prompt_version=metadata["prompt_version"],
            pipeline_name=metadata["pipeline_name"],
            output_schema_id=metadata["output_schema_id"],
            output_schema_version=metadata["output_schema_version"],
            template=metadata["template"],
            template_path=str(path.relative_to(self.root)),
            template_hash=_sha256(metadata["template"]),
        )


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
