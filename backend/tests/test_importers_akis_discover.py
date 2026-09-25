import textwrap

from app.importers.akis_petretzikis import _parse_sitemap, discover
from app.importers.base import DiscoveryOptions


def test_parse_sitemap_extracts_recipe_urls():
    xml = textwrap.dedent(
        """
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://akispetretzikis.com/</loc></url>
          <url><loc>https://akispetretzikis.com/recipe/1006/peinirli-sokolatas</loc></url>
          <url><loc>https://akispetretzikis.com/en/recipe/1006/peinirli-sokolatas</loc></url>
          <url><loc>https://akispetretzikis.com/recipe/102/pagwto-pralina-sokolatas</loc></url>
          <url><loc>https://akispetretzikis.com/blog/something</loc></url>
        </urlset>
        """
    )
    ids = _parse_sitemap(xml)
    assert ids == [("1006", "peinirli-sokolatas"), ("102", "pagwto-pralina-sokolatas")]


def test_discover_filters_and_limits(monkeypatch):
    xml = (
        "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">"
        """
        <url><loc>https://akispetretzikis.com/recipe/1/one</loc></url>
        <url><loc>https://akispetretzikis.com/recipe/2/two</loc></url>
        <url><loc>https://akispetretzikis.com/recipe/3/three</loc></url>
        </urlset>
        """
    )

    class FakeResp:
        def __init__(self, text):
            self.text = text

    def fake_get(url, max_retries=5):
        return FakeResp(xml)

    monkeypatch.setattr("app.importers.http.get", lambda u: FakeResp(xml))

    opts = DiscoveryOptions(limit=2)
    ids = list(discover(opts))
    assert ids == ["1", "2"]

    opts2 = DiscoveryOptions(ids=["3", "1"])
    ids2 = list(discover(opts2))
    assert ids2 == ["3", "1"]

    # ids absent should raise
    opts3 = DiscoveryOptions(ids=["999"])
    try:
        list(discover(opts3))
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for missing id")
