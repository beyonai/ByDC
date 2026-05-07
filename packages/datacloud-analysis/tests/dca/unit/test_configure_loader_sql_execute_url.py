"""configure_loader 透传 sql_execute_url 测试（chatbi 对接方案）。"""

from __future__ import annotations

from unittest.mock import patch

from datacloud_data_sdk.ontology.loader import OntologyLoader


def test_configure_loader_propagates_sql_execute_url() -> None:
    from datacloud_analysis.tools.ontology_tool_loader import configure_loader

    loader = OntologyLoader()
    with (
        patch("datacloud_analysis.tools.ontology_tool_loader.LangGraphPlanGenerator"),
        patch("datacloud_analysis.tools.ontology_tool_loader.TermLoader"),
    ):
        configure_loader(
            loader,
            model="kimi-k2.6",
            sql_execute_url="http://chatbi.example/api/sql",
        )

    assert loader.sql_execute_url == "http://chatbi.example/api/sql"


def test_configure_loader_default_sql_execute_url_is_none() -> None:
    from datacloud_analysis.tools.ontology_tool_loader import configure_loader

    loader = OntologyLoader()
    with (
        patch("datacloud_analysis.tools.ontology_tool_loader.LangGraphPlanGenerator"),
        patch("datacloud_analysis.tools.ontology_tool_loader.TermLoader"),
    ):
        configure_loader(loader, model="kimi-k2.6")

    assert loader.sql_execute_url is None
