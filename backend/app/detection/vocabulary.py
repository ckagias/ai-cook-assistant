"""The detector vocabulary: one canonical class list shared by both detector backends,
the preview UI, and the recipe importer's ingredient/equipment linking.

Deliberately free of any ML dependency so the base app (and its tests) can load it
without ultralytics/mediapipe installed.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, PrivateAttr, model_validator

VOCABULARY_PATH = Path(__file__).resolve().parent / "vocabulary.json"


class VocabClass(BaseModel):
    id: str
    group: str
    en: str
    el: str
    # Text prompts for the open-vocabulary backend. Several prompts may map to one class
    # (e.g. "frying pan" and "wok"); their detections are merged after inference.
    prompts: list[str]
    # Open Images V7 display names that map onto this class for the closed-vocabulary backend.
    oiv7: list[str] = Field(default_factory=list)
    hazard: bool = False
    # Part of every per-recipe vocabulary (hands, core cookware, hazards).
    base: bool = False
    # A cooking-state or hazard class a pretrained detector is not expected to get right.
    experimental: bool = False
    synonyms: dict[str, list[str]] = Field(default_factory=dict)


class Vocabulary(BaseModel):
    version: int
    groups: list[str]
    classes: list[VocabClass]

    _by_id: dict[str, VocabClass] = PrivateAttr(default_factory=dict)

    @model_validator(mode="after")
    def _check_consistency(self) -> "Vocabulary":
        seen_ids: set[str] = set()
        seen_prompts: set[str] = set()
        seen_oiv7: set[str] = set()
        for cls in self.classes:
            if cls.id in seen_ids:
                raise ValueError(f"duplicate vocabulary id: {cls.id}")
            seen_ids.add(cls.id)
            if cls.group not in self.groups:
                raise ValueError(f"{cls.id}: unknown group {cls.group!r}")
            if not cls.prompts:
                raise ValueError(f"{cls.id}: needs at least one prompt")
            for prompt in cls.prompts:
                if prompt in seen_prompts:
                    raise ValueError(f"{cls.id}: prompt {prompt!r} is used by another class")
                seen_prompts.add(prompt)
            for name in cls.oiv7:
                if name in seen_oiv7:
                    raise ValueError(f"{cls.id}: Open Images class {name!r} is mapped twice")
                seen_oiv7.add(name)
        return self

    def by_id(self, class_id: str) -> Optional[VocabClass]:
        return self._index().get(class_id)

    def ids(self) -> list[str]:
        return [c.id for c in self.classes]

    def base_ids(self) -> set[str]:
        return {c.id for c in self.classes if c.base}

    def prompt_list(self) -> list[str]:
        """Every prompt, in a stable order - the class order an exported YOLOE model bakes in."""
        return [p for c in self.classes for p in c.prompts]

    def prompt_to_id(self) -> dict[str, str]:
        return {p: c.id for c in self.classes for p in c.prompts}

    def oiv7_to_id(self) -> dict[str, str]:
        return {name: c.id for c in self.classes for name in c.oiv7}

    def fingerprint(self) -> str:
        """Short hash of the prompt list - part of an exported YOLOE file name, since the
        vocabulary is baked into the exported weights and a changed list needs a re-export."""
        return hashlib.sha1("\n".join(self.prompt_list()).encode("utf-8")).hexdigest()[:8]

    def _index(self) -> dict[str, VocabClass]:
        if not self._by_id:
            self._by_id = {c.id: c for c in self.classes}
        return self._by_id


@lru_cache(maxsize=1)
def load_vocabulary(path: Path = VOCABULARY_PATH) -> Vocabulary:
    return Vocabulary.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
