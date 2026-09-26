"""Any-URL importer. Hand-written HTML fixtures (not copies of real sites); the HTTP layer is
always faked - no test touches the network."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import recipes
from app.importers import enrich, generic

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "recipes_html"
URL = "https://recipes.example.com/tomato-soup"


def page(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.content = text.encode("utf-8")


class FakeHttp:
    """Stands in for importers/http.get. `pages` maps URL -> body, or an Exception to raise."""

    def __init__(self, pages: dict):
        self.pages = pages
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs.get("user_agent")))
        body = self.pages.get(url)
        if isinstance(body, Exception):
            raise body
        if body is None:
            raise RuntimeError(f"request to {url!r} returned non-retryable status: 404")
        return FakeResponse(body)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "import.db"))
    generic._robots_cache.clear()
    yield
    generic._robots_cache.clear()


def fake_http(monkeypatch, pages):
    fake = FakeHttp(pages)
    monkeypatch.setattr(generic.http, "get", fake)
    return fake


# ---------------------------------------------------------------- parsing


def test_full_english_page_maps_every_field():
    f = generic.parse_recipe_html(page("full_recipe_en.html"), URL)
    assert f["title"] == "Roasted Tomato Soup"
    assert f["language"] == "en"
    assert (f["prep_min"], f["cook_min"], f["total_min"]) == (15, 45, 60)
    assert f["yields"] == "4 servings"
    assert f["author"] == "Test Cook"
    assert f["equipment"] == ["large pot", "blender"]  # from schema.org `tool`
    assert f["nutrients"]["calories"] == "180 kcal"
    assert len(f["ingredients"]) == 6 and len(f["instructions"]) == 4


def test_staged_recipe_carries_suggestions_and_links_to_detector_classes():
    f = generic.parse_recipe_html(page("full_recipe_en.html"), URL)
    r = generic.build_staged_recipe(f, URL, "2026-09-25T00:00:00Z")
    assert r.id == generic.staged_id_for(URL) and r.id.startswith("s-")
    assert [s.suggested_duration_sec for s in r.steps] == [None, 35 * 60, 10 * 60, None]
    assert all(not s.checkable and not s.contains_raw_protein for s in r.steps)  # a human decides these
    by_line = {d.raw_text: d for d in r.ingredient_details}
    assert (by_line["1 kg tomatoes"].quantity, by_line["1 kg tomatoes"].unit, by_line["1 kg tomatoes"].vocab_id) == ("1", "kg", "tomato")
    assert by_line["salt and pepper"].vocab_id == "salt_pepper"
    equipment = {e.name: (e.vocab_id, e.inferred) for e in r.equipment}
    assert equipment["large pot"] == ("pot", False)
    assert equipment["oven"] == ("oven", True)  # inferred from "Preheat the oven"
    assert equipment["knife"] == ("knife", True)


def test_greek_page():
    url = "https://recipes.example.com/moussaka"
    f = generic.parse_recipe_html(page("greek_recipe.html"), url)
    r = generic.build_staged_recipe(f, url, "2026-09-25T00:00:00Z")
    assert r.language == "el" and r.name == {"el": "Μουσακάς"}
    # "λεπτές φέτες" (thin slices) is not a duration; ranges count at their upper end.
    assert [s.suggested_duration_sec for s in r.steps] == [None, 600, 50 * 60, 3600]
    by_line = {d.raw_text: d for d in r.ingredient_details}
    assert (by_line["500 γρ. κιμά μοσχαρίσιο"].unit, by_line["500 γρ. κιμά μοσχαρίσιο"].vocab_id) == ("γρ.", "raw_meat")
    assert by_line["2 αυγά"].vocab_id == "egg"
    assert {e.vocab_id for e in r.equipment} >= {"frying_pan", "pot", "baking_tray", "oven"}


def test_minimal_page_tolerates_missing_optional_fields():
    f = generic.parse_recipe_html(page("minimal_recipe.html"), URL)
    r = generic.build_staged_recipe(f, URL, "2026-09-25T00:00:00Z")
    assert r.times is None and r.servings is None and r.equipment == []
    assert r.steps[0].instruction == {"en": "Toast the bread."}


def test_page_without_a_recipe_is_rejected():
    with pytest.raises(Exception):
        generic.parse_recipe_html(page("not_a_recipe.html"), URL)


@pytest.mark.parametrize(
    "text,seconds",
    [
        ("Bake for 25 minutes.", 1500),
        ("Simmer 10-15 min, then rest 5 minutes.", 1200),
        ("Cook for 1 hour", 3600),
        ("Βράστε για 8 λεπτά.", 480),
        ("Ψήστε 1 ώρα και 15 λεπτά.", 4500),
        ("Κόψτε σε λεπτές φέτες.", None),
        ("Preheat the oven to 180C.", None),
    ],
)
def test_duration_parsing(text, seconds):
    assert enrich.duration_seconds(text) == seconds


# ---------------------------------------------------------------- import flow


def test_import_stages_the_recipe_with_an_honest_user_agent(monkeypatch):
    fake = fake_http(monkeypatch, {"https://recipes.example.com/robots.txt": "User-agent: *\nAllow: /", URL: page("full_recipe_en.html")})
    result = generic.import_url(URL)
    assert result.status == "staged"
    assert fake.calls[-1] == (URL, generic.HONEST_UA)
    staged = recipes.get_recipe(result.recipe_id, status=recipes.STAGED)
    assert staged.name == {"en": "Roasted Tomato Soup"} and staged.times.total_min == 60
    assert recipes.get_recipe(result.recipe_id) is None  # not served until curated
    assert recipes.source_payload(result.recipe_id)["title"] == "Roasted Tomato Soup"


def test_reimport_within_a_week_does_not_fetch_again(monkeypatch):
    fake = fake_http(monkeypatch, {URL: page("full_recipe_en.html")})  # no robots.txt -> allowed
    assert generic.import_url(URL).status == "staged"
    fetches = len(fake.calls)
    assert generic.import_url(URL).status == "skipped"
    assert len(fake.calls) == fetches
    later = lambda: datetime.now(timezone.utc) + timedelta(days=8)  # noqa: E731
    assert generic.import_url(URL, now=later).status == "staged"
    assert generic.import_url(URL, force=True).status == "staged"


def test_robots_disallow_blocks_before_the_page_is_fetched(monkeypatch):
    fake = fake_http(monkeypatch, {"https://recipes.example.com/robots.txt": "User-agent: *\nDisallow: /", URL: page("full_recipe_en.html")})
    result = generic.import_url(URL)
    assert result.status == "blocked"
    assert URL not in [u for u, _ in fake.calls]


def test_unreachable_robots_txt_is_treated_as_disallowed(monkeypatch):
    fake_http(monkeypatch, {"https://recipes.example.com/robots.txt": RuntimeError("failed after 2 attempts: status=503"),
                            URL: page("full_recipe_en.html")})
    assert generic.import_url(URL).status == "blocked"


def test_a_published_recipe_is_never_overwritten_by_reimport(monkeypatch):
    fake_http(monkeypatch, {URL: page("full_recipe_en.html")})
    staged_id = generic.import_url(URL).recipe_id
    curated = recipes.get_recipe(staged_id, status=None).model_copy(update={"id": "tomato-soup"})
    recipes.publish(curated, replaces=staged_id)
    result = generic.import_url(URL, force=True)
    assert result.status == "skipped" and result.recipe_id == "tomato-soup"


def test_bad_page_fails_without_stopping_anything(monkeypatch):
    fake_http(monkeypatch, {URL: page("not_a_recipe.html")})
    result = generic.import_url(URL)
    assert result.status == "failed"
    assert recipes.find_source(URL) is None


def test_non_http_url_is_refused():
    assert generic.import_url("file:///etc/passwd").status == "failed"


def test_published_import_narrows_the_detector_vocabulary(monkeypatch):
    fake_http(monkeypatch, {URL: page("full_recipe_en.html")})
    staged_id = generic.import_url(URL).recipe_id
    recipes.publish(recipes.get_recipe(staged_id, status=None).model_copy(update={"id": "tomato-soup"}), replaces=staged_id)
    allowed = recipes.detection_vocabulary("tomato-soup")
    assert {"tomato", "onion", "garlic", "blender", "pot", "hand"} <= allowed
    assert "banana" not in allowed


def test_sitemap_index_is_followed_filtered_and_limited(monkeypatch):
    index = """<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://s.example/sm-1.xml</loc></sitemap></sitemapindex>"""
    child = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://s.example/recipe/a</loc></url><url><loc>https://s.example/blog/x</loc></url>
      <url><loc>https://s.example/recipe/b</loc></url><url><loc>https://s.example/recipe/c</loc></url></urlset>"""
    fake_http(monkeypatch, {"https://s.example/sitemap.xml": index, "https://s.example/sm-1.xml": child})
    urls = generic.discover_sitemap("https://s.example/sitemap.xml", pattern="/recipe/", limit=2)
    assert urls == ["https://s.example/recipe/a", "https://s.example/recipe/b"]
