import importlib
import types
import os
import json


def make_dummy_importer(tmp_path, module_name="app.importers.dummy"):
    # Create a dummy module object that resembles the real importer API
    mod = types.SimpleNamespace()

    class DummyOptions:
        def __init__(self, category=None, ids=None, limit=None):
            self.category = category
            self.ids = ids
            self.limit = limit

    def discover(options):
        # return a few fake ids
        vals = ["r1", "r2", "r3"]
        if options.limit:
            return vals[: options.limit]
        return vals

    def fetch_normalize_and_stage(rid, force_refetch=False):
        staged = {"source_id": rid, "title": f"Recipe {rid}"}
        staging_dir = tmp_path / "backend" / "data" / "imported_recipes_staging" / "dummy"
        staging_dir.mkdir(parents=True, exist_ok=True)
        path = staging_dir / f"{rid}.json"
        path.write_text(json.dumps(staged, ensure_ascii=False))
        # update manifest
        manifest = staging_dir / "manifest.json"
        m = {rid: {"source_id": rid}}
        manifest.write_text(json.dumps(m))
        return staged

    mod.DiscoveryOptions = DummyOptions
    mod.discover = discover
    mod.fetch_normalize_and_stage = fetch_normalize_and_stage

    return mod


def test_import_recipes_end_to_end(monkeypatch, tmp_path):
    # Install dummy importer into sys.modules under the expected name
    dummy_mod = make_dummy_importer(tmp_path)
    monkeypatch.setitem(__import__("sys").modules, "app.importers.dummy", dummy_mod)

    # Patch SITES registry in the script to point to our dummy importer
    import import_recipes as script

    script.SITES["dummy"] = "app.importers.dummy"

    # Run the script programmatically
    rc = script.run_site("dummy", ids=[], category=None, limit=2, all_flag=False, force_refetch=False)
    assert rc == 0

    # Check that staged files were written
    staging_dir = tmp_path / "backend" / "data" / "imported_recipes_staging" / "dummy"
    files = list(staging_dir.glob("*.json"))
    assert any(p.name == "r1.json" or p.name == "r2.json" for p in files)
