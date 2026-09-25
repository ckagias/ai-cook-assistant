from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel


class StagedIngredient(BaseModel):
    title: Dict[str, str]
    quantity: str = ""
    unit: Dict[str, str] = {}
    info: Dict[str, str] = {}


class StagedStep(BaseModel):
    section: Dict[str, str]
    text: Dict[str, str]


class StagedMetadata(BaseModel):
    make_time_min: Optional[int] = None
    bake_time_min: Optional[int] = None
    servings: Optional[str] = None
    difficulty: Optional[str] = None
    dietary_flags: Dict[str, bool] = {}
    equipment: List[str] = []
    image_url: Optional[str] = None
    video_url: Optional[str] = None


class StagedRecipe(BaseModel):
    source: str
    source_id: str
    source_url: Dict[str, str]
    fetched_at: str
    title: Dict[str, str]
    category: Dict[str, str] = {}
    ingredients: List[StagedIngredient] = []
    steps: List[StagedStep] = []
    metadata: StagedMetadata = StagedMetadata()
