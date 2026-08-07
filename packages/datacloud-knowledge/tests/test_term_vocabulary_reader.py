"""测试 term_vocabulary 读取侧协议（T6）。

覆盖：
- ``PostgresTermReader.list_vocabulary()`` 全量读取 term_vocabulary 表
  （sqlite 内存库 + 注入 session_factory，参照 test_enumerate_object_instances 模式）
- ``FakeTermReader`` / ``FakeTermWriter`` 同步（协议完整性，不抛 NotImplementedError）
"""

from __future__ import annotations

import pytest
from datacloud_knowledge.adapters.opengauss._readers import _base as _reader_base
from datacloud_knowledge.adapters.opengauss.reader import PostgresTermReader
from fakes import FakeTermReader, FakeTermWriter
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

_WORDS = ("苹果", "华为", "苹果公司", "张三")


def _make_reader(monkeypatch: pytest.MonkeyPatch, words: tuple[str, ...]) -> PostgresTermReader:
    """构造 sqlite 内存库 + term_vocabulary 表，返回注入 session_factory 的 reader。"""
    monkeypatch.setattr(_reader_base, "_SCHEMA_CHECKED", True)
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE term_vocabulary ("
                "vocab_id INTEGER PRIMARY KEY, word VARCHAR(255) NOT NULL)"
            )
        )
        for word in words:
            conn.execute(text("INSERT INTO term_vocabulary (word) VALUES (:w)"), {"w": word})
        conn.commit()
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False)
    return PostgresTermReader(session_factory=factory)


@pytest.fixture()
def vocab_reader(monkeypatch: pytest.MonkeyPatch) -> PostgresTermReader:
    """预置 4 个词的 sqlite 词典读取器。"""
    return _make_reader(monkeypatch, _WORDS)


class TestListVocabularyReader:
    def test_returns_all_distinct_words(self, vocab_reader: PostgresTermReader) -> None:
        words = vocab_reader.list_vocabulary()
        assert isinstance(words, list)
        assert set(words) == set(_WORDS)
        assert len(words) == len(_WORDS)

    def test_preserves_duplicate_rows_as_projected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """表约束层负责去重；reader 只做全量投影读取（含投影内重复行原样返回）。"""
        reader = _make_reader(monkeypatch, ("苹果", "苹果", "华为"))
        assert reader.list_vocabulary() == ["苹果", "苹果", "华为"]

    def test_empty_table_returns_empty_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        reader = _make_reader(monkeypatch, ())
        assert reader.list_vocabulary() == []


class TestVocabularyFakes:
    def test_fake_reader_returns_preset_words(self) -> None:
        reader = FakeTermReader().set_vocabulary("苹果", "华为")
        assert reader.list_vocabulary() == ["苹果", "华为"]

    def test_fake_reader_defaults_to_empty(self) -> None:
        assert FakeTermReader().list_vocabulary() == []

    def test_fake_writer_list_vocabulary_returns_empty(self) -> None:
        assert FakeTermWriter().list_vocabulary() == []
