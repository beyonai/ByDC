from __future__ import annotations


def test_cli_entrypoint_module_exists() -> None:
    from datacloud_analysis.cli import main

    assert callable(main)
