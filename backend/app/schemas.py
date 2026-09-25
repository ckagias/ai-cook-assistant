from typing import Literal, Optional

from pydantic import BaseModel, Field


class SafetyFlag(BaseModel):
    severity: Literal["alarm", "caution"]
    reason: str


class AnalyzeRequest(BaseModel):
    mode: Literal["identify", "read_label", "check_doneness", "scene_description"]
    image_base64: str
    detail_level: Literal["brief", "detailed"] = "brief"
    language: Literal["el", "en"] = "el"
    recipe_id: Optional[str] = None
    step_index: Optional[int] = None
    prior_context: Optional[str] = None
    user_followup: Optional[str] = None
    # Deliberately NO reference_image field - backend resolves it server-side.


class AnalyzeResponse(BaseModel):
    description: str
    primary_subject: str
    camera_feedback: Optional[str] = None
    doneness_stage: Optional[str] = None
    confidence: Literal["high", "medium", "low"]
    evidence: list[str] = Field(default_factory=list)  # no max_length, truncation happens in vision.py
    alternate_guesses: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    clarifying_question: Optional[str] = None
    raw_protein_detected: bool = False
    safety_flag: Optional[SafetyFlag] = None
    spoken_response: str


class RecipeStep(BaseModel):
    index: int
    instruction: dict[str, str]
    expected_duration_sec: Optional[int] = None
    checkable: bool = False
    check_prompt_hint: Optional[str] = None
    reference_image: Optional[str] = None
    contains_raw_protein: bool = False


class RecipeSource(BaseModel):
    site: str
    source_id: str
    url: dict[str, str]
    imported_at: str


class Recipe(BaseModel):
    id: str
    name: dict[str, str]
    aliases: dict[str, list[str]]
    ingredients: list[str]
    steps: list[RecipeStep]
    source: Optional[RecipeSource] = None
