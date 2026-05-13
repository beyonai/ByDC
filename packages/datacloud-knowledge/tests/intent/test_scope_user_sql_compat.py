from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from datacloud_knowledge.contracts.types import UserScopedNameItem


@pytest.mark.intent
def test_user_name_cache_query_uses_scope_user_id_filter() -> None:
    """Verify cache.load() delegates to create_reader().get_user_scoped_names()."""
    from datacloud_knowledge.intent.cache import UserNameCache

    mock_item = UserScopedNameItem(
        name_text="alias1",
        term_id="t1",
        term_type_code="prop",
        search_scope={"scope_user_id": "test-user", "score": 0.8},
    )
    mock_reader = MagicMock()
    mock_reader.get_user_scoped_names.return_value = [mock_item]

    with patch(
        "datacloud_knowledge.intent.cache.create_reader",
        return_value=mock_reader,
    ):
        cache = UserNameCache()
        name_index = cache.load("test-user")

    mock_reader.get_user_scoped_names.assert_called_once_with(user_id="test-user")
    assert "alias1" in name_index
    assert name_index["alias1"] == [("t1", "prop", "alias", 0.8)]
