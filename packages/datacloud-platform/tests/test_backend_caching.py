"""Tests for backend instance caching in DatacloudPlatform._get_backend().

Cache key is ``{type_name}:{impl_name}`` — same pair reuses the same instance.
"""

from __future__ import annotations

from datacloud_platform import DatacloudPlatform, OntologyBaseEntry

LOCAL = "local-base"
REMOTE = "remote-base"


def test_same_type_impl_same_instance(platform: DatacloudPlatform) -> None:
    """Two calls with same (type_name, impl_name) return the identical instance."""
    b1 = platform._get_backend("ontology", "fake-data")
    b2 = platform._get_backend("ontology", "fake-data")
    assert b1 is b2


def test_different_type_different_instance(platform: DatacloudPlatform) -> None:
    """Different type_name produces a different instance even if impl_name matches."""
    onto = platform._get_backend("ontology", "fake-data")
    know = platform._get_backend("term", "fake-knowledge")
    assert onto is not know


def test_two_local_bases_share_ontology(platform: DatacloudPlatform) -> None:
    """Two LOCAL bases both resolve to ('ontology', 'fake-data') → same instance."""
    onto_local, *_ = platform._fakes  # type: ignore[attr-defined]

    # Register a second LOCAL base
    entry2 = OntologyBaseEntry(
        base_id="local-base-2",
        display_name="本地库2",
        source_type="LOCAL",
    )
    platform.create_base(entry2)

    # Resolve ontology for both bases — they share the same cached instance
    b1 = platform._ontology_for(LOCAL)
    b2 = platform._ontology_for("local-base-2")
    assert b1 is b2
    assert b1 is onto_local

    # Cache is populated
    assert platform._backend_cache.get("ontology:fake-data") is onto_local


def test_local_remote_different_ontology_instance(platform: DatacloudPlatform) -> None:
    """LOCAL resolves to 'fake-data', REMOTE resolves to 'remote-http' → different instances."""
    onto_local, onto_remote, *_ = platform._fakes  # type: ignore[attr-defined]

    b_local = platform._ontology_for(LOCAL)
    b_remote = platform._ontology_for(REMOTE)

    assert b_local is onto_local
    assert b_remote is onto_remote
    assert b_local is not b_remote


def test_cache_key_format(platform: DatacloudPlatform) -> None:
    """Cache key is '{type_name}:{impl_name}'."""
    platform._get_backend("ontology", "fake-data")
    assert "ontology:fake-data" in platform._backend_cache
