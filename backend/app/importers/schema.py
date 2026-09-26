from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StagedIngredient(BaseModel):
    title: dict[str, str]
    quantity: str = ""
    unit: dict[str, str] = Field(default_factory=dict)
    info: dict[str, str] = Field(default_factory=dict)


class StagedStep(BaseModel):
    section: dict[str, str]
    text: dict[str, str]
    # Parsed from the text by the importer ("bake for 25 minutes"); the curator confirms it.
    suggested_duration_sec: int | None = None


class StagedMetadata(BaseModel):
    make_time_min: int | None = None
    bake_time_min: int | None = None
    servings: str | None = None
    difficulty: str | None = None
    dietary_flags: dict[str, bool] = Field(default_factory=dict)
    equipment: list[str] = Field(default_factory=list)
    image_url: str | None = None
    video_url: str | None = None


class StagedRecipe(BaseModel):
    source: str
    source_id: str
    source_url: dict[str, str]
    fetched_at: str
    title: dict[str, str]
    category: dict[str, str] = Field(default_factory=dict)
    ingredients: list[StagedIngredient]
    steps: list[StagedStep]
    metadata: StagedMetadata
