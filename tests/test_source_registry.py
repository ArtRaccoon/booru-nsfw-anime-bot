from app.providers.catalog import CatalogEntry
from app.providers.prober import ProbeResult
from app.providers.source_registry import STATUS_AVAILABLE, SourceRegistry


def test_source_registry_import_enable_disable_stats(tmp_path):
    reg = SourceRegistry(tmp_path / "registry.json")
    summary = reg.import_entries(
        [
            CatalogEntry(
                slug="konachan", name="Konachan", base_url="https://konachan.com", engine="moebooru"
            )
        ]
    )
    assert summary == {"imported": 1, "updated": 0, "total": 1}
    assert reg.enable("konachan") is True
    assert reg.stats()["enabled"] == 1
    assert reg.disable("konachan") is True
    assert SourceRegistry(tmp_path / "registry.json").load().sources["konachan"].enabled is False


def test_source_registry_apply_probe_tracks_success_rate(tmp_path):
    reg = SourceRegistry(tmp_path / "registry.json")
    reg.import_entries(
        [CatalogEntry(slug="x", name="X", base_url="https://x.test", engine="danbooru")]
    )
    rec = reg.sources["x"]
    reg._apply_probe(rec, ProbeResult("available", 200, engine="danbooru"), 0.25)
    assert rec.available == STATUS_AVAILABLE
    assert rec.success_rate == 1
    assert rec.response_time == 0.25
