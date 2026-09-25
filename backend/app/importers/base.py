from dataclasses import dataclass
from typing import Iterator, Protocol


@dataclass
class DiscoveryOptions:
    category: str | None = None
    ids: list[str] | None = None
    limit: int | None = None


class RecipeSource(Protocol):
    site_id: str  # e.g. "akis_petretzikis" - matches the staged JSON's "source" field

    def discover(self, options: DiscoveryOptions) -> Iterator[str]:
        """Yield source-specific recipe identifiers (not full URLs) to fetch."""

    def fetch_and_normalize(self, recipe_id: str) -> dict:
        """Fetch one recipe and return it in the staged schema.

        Phase 5 will define StagedRecipe in schema.py. Expected shape (stub):
        source, source_id, source_url {el, en}, fetched_at, title {el, en},
        category, ingredients, steps, metadata.
        """
