from typing import Literal, Optional

from pydantic import BaseModel, Field


class SafetyFlag(BaseModel):
    severity: Literal["alarm", "caution"]
    reason: str


# How the cook likes meat done, rarest first. Only recipes whose steps carry `by_doneness`
# targets offer the choice.
Doneness = Literal["rare", "medium_rare", "medium", "medium_well", "well_done"]
DONENESS_ORDER: tuple[str, ...] = ("rare", "medium_rare", "medium", "medium_well", "well_done")


class AnalyzeRequest(BaseModel):
    mode: Literal["identify", "read_label", "check_doneness", "scene_description", "check_ingredients"]
    image_base64: str
    detail_level: Literal["brief", "detailed"] = "brief"
    language: Literal["el", "en"] = "el"
    recipe_id: Optional[str] = None
    step_index: Optional[int] = None
    prior_context: Optional[str] = None
    user_followup: Optional[str] = None
    # Deliberately NO reference_image field - backend resolves it server-side.
    doneness_preference: Optional[Doneness] = None
    # The step timer the cook started (timers never start on their own): how far along it is
    # helps judge "is it ready" from colour *and* time.
    timer_elapsed_sec: Optional[int] = Field(default=None, ge=0, le=86400)
    timer_total_sec: Optional[int] = Field(default=None, ge=0, le=86400)


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
    # check_doneness: can the cook move on? "ready" is only a proposal - the app asks the cook
    # before it advances, and main.py strips it wherever looks can't be trusted (raw protein).
    # No numeric constraints here on purpose: every provider builds its schema from this class,
    # so bounds are enforced in main.py instead.
    verdict: Optional[Literal["ready", "not_ready", "unsure"]] = None
    suggested_extra_sec: Optional[int] = None  # not_ready: roughly how much longer
    ingredients_seen: list[int] = Field(default_factory=list)  # check_ingredients: 1-based numbers
    spoken_response: str


class DonenessTarget(BaseModel):
    temp_c: int  # take it off the heat when the thickest part reads this
    duration_sec: Optional[int] = None  # this step's usual time for that doneness


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
    # "prep" = cutting, mixing, seasoning: a check judges the work (piece size, evenness), never
    # doneness. "cook" = heat is on. "rest" = waiting. Curated, like contains_raw_protein.
    kind: Optional[Literal["prep", "cook", "rest"]] = None
    by_doneness: dict[Doneness, DonenessTarget] = Field(default_factory=dict)


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
    text: dict[str, str] = Field(default_factory=dict)  # per-language display text; raw_text otherwise


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


# --- POST /voice: push-to-talk commands ---

# Everything a voice command can make the app do. A closed list on purpose: whatever the
# microphone picks up (a TV, a visitor, words that reach the model any other way), the model
# can only ever pick one of these - it cannot invent an action.
VoiceAction = Literal[
    "next_step", "previous_step", "repeat_step", "start_timer", "add_time", "stop_timer",
    "check_doneness", "check_ingredients", "list_ingredients", "identify", "find_recipe",
    "choose_recipe", "set_doneness", "stop_recipe", "yes", "no", "answer", "unclear",
]

# A question the app asked and is waiting on - "yes"/"no" only mean something against one.
PendingQuestion = Literal["advance", "add_time", "clarify", "stop_recipe", "check_offer"]


class VoiceCommand(BaseModel):
    """What the language model returns for one spoken request (structured output)."""

    action: VoiceAction
    timer_seconds: Optional[int] = None  # start_timer: duration; add_time: change (+ more, - less)
    search_words: list[str] = Field(default_factory=list)  # find_recipe, in Greek and English
    choice: Optional[int] = None  # choose_recipe: 1-based number of an offered recipe
    doneness: Optional[Doneness] = None  # set_doneness
    spoken_response: str


class RecipeCandidate(BaseModel):
    id: str
    name: dict[str, str]


class VoiceResponse(BaseModel):
    heard: str  # the transcript, shown on screen so a misheard command is visible
    action: VoiceAction
    timer_seconds: Optional[int] = None
    recipe_id: Optional[str] = None  # choose_recipe, already validated against the database
    candidates: list[RecipeCandidate] = Field(default_factory=list)  # find_recipe results
    doneness: Optional[Doneness] = None
    spoken_response: str


class VoiceTextRequest(BaseModel):
    """POST /voice/text: words the browser already recognized (wake word, talk button) or the cook
    typed (for someone who can't speak). Same understanding and checks as /voice, no audio."""

    text: str = Field(min_length=1, max_length=500)
    language: Literal["el", "en"] = "el"
    recipe_id: Optional[str] = None
    step_index: Optional[int] = None
    candidates: list[str] = Field(default_factory=list, max_length=5)
    pending: Optional[PendingQuestion] = None
    doneness: Optional[Doneness] = None
    timer_remaining_sec: Optional[int] = Field(default=None, ge=0, le=86400)
