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
    section: Optional[str] = None
    # Parsed from the step text at import ("simmer for 10 minutes"); a curator confirms it
    # into expected_duration_sec - it never starts a timer on its own.
    suggested_duration_sec: Optional[int] = None


class RecipeSource(BaseModel):
    site: str
    source_id: str
    url: dict[str, str]
    imported_at: str
    author: Optional[str] = None
    fetched_at: Optional[str] = None


class IngredientLine(BaseModel):
    raw_text: str
    quantity: Optional[str] = None
    unit: Optional[str] = None
    name: Optional[str] = None
    group: Optional[str] = None
    vocab_id: Optional[str] = None  # detector class, when one matches


class EquipmentItem(BaseModel):
    name: str
    vocab_id: Optional[str] = None
    inferred: bool = False  # guessed from the step text rather than listed by the source


class RecipeTimes(BaseModel):
    prep_min: Optional[int] = None
    cook_min: Optional[int] = None
    total_min: Optional[int] = None


class Recipe(BaseModel):
    id: str
    name: dict[str, str]
    aliases: dict[str, list[str]]
    ingredients: list[str]
    steps: list[RecipeStep]
    source: Optional[RecipeSource] = None
    # Everything below is optional metadata - the original three recipes have none of it.
    description: dict[str, str] = Field(default_factory=dict)
    language: Optional[str] = None
    servings: Optional[str] = None
    times: Optional[RecipeTimes] = None
    difficulty: Optional[str] = None
    cuisine: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    nutrition: dict[str, str] = Field(default_factory=dict)
    dietary: dict[str, bool] = Field(default_factory=dict)
    ingredient_details: list[IngredientLine] = Field(default_factory=list)
    equipment: list[EquipmentItem] = Field(default_factory=list)


# --- /detect: all coordinates normalized to 0-1 of the frame the client sent ---


class DetBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class DetPoint(BaseModel):
    x: float
    y: float


class DetectedObject(BaseModel):
    class_id: str
    label_en: str
    label_el: str
    group: str
    hazard: bool = False
    confidence: float
    box: DetBox
    center: DetPoint


class DetectedHand(BaseModel):
    handedness: str
    confidence: float
    box: DetBox
    fingertips: list[DetPoint] = Field(default_factory=list)


class HandRelation(BaseModel):
    hand: int  # index into `hands`
    object: int  # index into `detections`
    kind: Literal["touching", "over", "near"]
    distance: float


class DetectLatency(BaseModel):
    decode: float
    queue: float = 0.0  # waiting for the model (another frame in progress, or the first load)
    detect: float
    hands: float
    total: float


class DetectResponse(BaseModel):
    model: str
    width: int
    height: int
    latency_ms: DetectLatency
    detections: list[DetectedObject]
    hands: list[DetectedHand]
    relations: list[HandRelation]
