"""Backend name resolution — 3-layer overlay: default → preset → manual.

Used by DatacloudPlatform._resolve_names() to compute the complete
{type_name: impl_name} mapping for a given OntologyBaseEntry.
"""

from __future__ import annotations

from datacloud_platform.backends.presets import _PRESETS
from datacloud_platform.backends.registry import _BACKEND_DEFAULTS


def resolve_backend_names(
    source_type: str,
    manual: dict[str, str],
) -> dict[str, str]:
    """Three-layer overlay: defaults → preset → manual fine-grained.

    Args:
        source_type: Coarse preset name.  Empty string skips the preset layer.
        manual: Manual dimension→impl overrides.  Empty values are skipped
                (they do NOT clear the layer below).

    Returns:
        Complete {type_name: impl_name} mapping.

    Raises:
        ValueError: If source_type names an unknown preset.

    Resolution table:

        | source_type | manual_backends                              | result                                       |
        |-------------|----------------------------------------------|----------------------------------------------|
        | "LOCAL"     | {}                                           | all defaults                                 |
        | "REMOTE"    | {}                                           | ontology=remote-http, knowledge=remote-http,  |
        |             |                                              | execution=none, storage=none                 |
        | "LOCAL"     | {"knowledge": "remote-http"}                 | knowledge=remote-http, rest defaults          |
        | ""          | {"ontology": "datacloud-data", "exec": "none"} | ontology=datacloud-data, execution=none,     |
        |             |                                              | rest defaults                                |
    """
    # Layer 1: defaults
    result = dict(_BACKEND_DEFAULTS)

    # Layer 2: preset overlay
    if source_type:
        preset = _PRESETS.get(source_type)
        if preset is None:
            raise ValueError(
                f"Unknown preset '{source_type}'. "
                f"Available: {', '.join(sorted(_PRESETS))}"
            )
        for key in preset:
            if key not in _BACKEND_DEFAULTS:
                raise ValueError(
                    f"Unknown backend type '{key}' in preset '{source_type}'. "
                    f"Available: {', '.join(sorted(_BACKEND_DEFAULTS))}"
                )
        result.update(preset)

    # Layer 3: manual fine-grained overlay (empty values skipped)
    result.update({k: v for k, v in manual.items() if v})

    return result
