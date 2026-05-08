"""术语集加载与解析：code / label / aliases 多维匹配。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from datacloud_data_sdk.exceptions import TermAmbiguousError, TermNotFoundError

search_terms_by_type: Callable[..., Any] | None
try:
    from datacloud_knowledge.provider import search_terms_by_type as _search_terms_by_type
except ImportError:
    search_terms_by_type = None
else:
    search_terms_by_type = _search_terms_by_type


@dataclass
class TermEntry:
    code: str
    label: str
    aliases: list[str] = field(default_factory=list)


class TermLoader(ABC):
    """术语集加载器抽象接口。"""

    @abstractmethod
    def resolve_code(
        self,
        term_set: str,
        value: str,
        dataset_id: int | None = None,
        term_type_code: str | None = None,
        keyword: str | None = None,
        param_name: str | None = None,
    ) -> str:
        """将标签/别名/code 解析为标准 code。"""

    @abstractmethod
    def resolve_value(
        self,
        term_set: str,
        value: str,
        term_field: str | None = None,
        dataset_id: int | None = None,
        term_type_code: str | None = None,
        keyword: str | None = None,
        param_name: str | None = None,
    ) -> str:
        """根据 term_field 解析为 code 或 label。term_field 为 'code' 时返回 code，为 'name' 时返回 label。"""

    @abstractmethod
    def get_available_values(
        self,
        term_set: str,
        dataset_id: int | None = None,
        term_type_code: str | None = None,
        keyword: str = "",
    ) -> list[str]:
        """返回术语集的所有标签值。"""

    @abstractmethod
    def get_codes(
        self,
        term_set: str,
        dataset_id: int | None = None,
        term_type_code: str | None = None,
    ) -> list[str]:
        """返回术语集的所有 code 值。"""

    @abstractmethod
    def get_entries(
        self,
        term_set: str,
        dataset_id: int | None = None,
        term_type_code: str | None = None,
        keyword: str = "",
    ) -> list[dict[str, str]]:
        """返回术语集的所有条目，每项包含 code 和 label。"""

    @classmethod
    def from_config(cls, config: dict) -> TermLoader:
        """根据配置返回 KbTermLoader。"""
        loader_type = str(config.get("type", "kb") or "kb").strip().lower()
        if loader_type != "kb":
            raise ValueError(f"Unsupported term loader type: {loader_type}")
        return KbTermLoader.from_config(config.get("kb", {}))


class KbTermLoader(TermLoader):
    """基于 knowledge_search 的术语加载器。"""

    def __init__(self, mapping: dict[str, list[dict[str, object]]] | None = None) -> None:
        self._sets: dict[str, list[TermEntry]] = {}
        self._cache: dict[tuple[str, str], list[TermEntry]] = {}
        if mapping:
            for term_set, entries in mapping.items():
                self._sets[term_set] = [
                    TermEntry(
                        code=str(e["code"]),
                        label=str(e["label"]),
                        aliases=[str(a) for a in e.get("aliases", [])],  # type: ignore[union-attr]
                    )
                    for e in entries
                ]

    @classmethod
    def from_config(cls, config: dict) -> KbTermLoader:
        return cls(mapping=config.get("mapping"))

    def _resolve_term_type_code(self, term_set: str, term_type_code: str | None) -> str:
        if term_type_code:
            return term_type_code
        if "." in term_set:
            return term_set.split(".")[0]
        return term_set

    def _mapping_entries(self, term_set: str) -> list[TermEntry]:
        return self._sets.get(term_set, [])

    def _search(self, term_type_code: str, keyword: str = "", limit: int = 100) -> list[TermEntry]:
        global search_terms_by_type
        if search_terms_by_type is None:
            raise ImportError("datacloud-knowledge is not installed")
        result = search_terms_by_type(
            term_type_code=term_type_code,
            keyword=keyword or None,
            limit=limit,
        )
        entries: list[TermEntry] = []
        for item in result.items:
            aliases: list[str] = []
            tags = item.term_tags
            if isinstance(tags, dict):
                syn = tags.get("synonyms", "")
                if syn:
                    aliases = [s.strip() for s in str(syn).split(",") if s.strip()]
            entries.append(
                TermEntry(
                    code=item.term_code,
                    label=item.term_name,
                    aliases=aliases,
                )
            )
        return entries

    def _get_cached_entries(self, term_type_code: str, keyword: str) -> list[TermEntry]:
        """按 term_type_code + keyword 获取缓存的术语搜索结果。"""
        cache_key = (term_type_code, keyword)
        cached = self._cache.get(cache_key)
        if not cached:
            cached = self._search(term_type_code, keyword=keyword)
            self._cache[cache_key] = cached
        return cached

    def resolve_code(
        self,
        term_set: str,
        value: str,
        dataset_id: int | None = None,
        term_type_code: str | None = None,
        keyword: str | None = None,
        param_name: str | None = None,
    ) -> str:
        """将标签/别名/code 解析为标准 code。lookup 时可用 keyword=value 搜索。

        Raises:
            TermAmbiguousError: 匹配到多个术语，需要用户选择
            TermNotFoundError: 术语不存在
        """
        memory_matches: list[dict[str, str]] = []
        for entry in self._mapping_entries(term_set):
            if value in (entry.code, entry.label, *entry.aliases):
                memory_matches.append({"code": entry.code, "label": entry.label})
        if len(memory_matches) == 1:
            return memory_matches[0]["code"]
        if len(memory_matches) > 1:
            raise TermAmbiguousError(term_set, value, memory_matches, param_name)

        tc = self._resolve_term_type_code(term_set, term_type_code)
        search_keyword = keyword or value
        cached = self._get_cached_entries(tc, search_keyword)
        matches: list[dict[str, str]] = []
        for entry in cached:
            if value in (entry.code, entry.label, *entry.aliases):
                matches.append({"code": entry.code, "label": entry.label})
        if len(matches) == 1:
            return matches[0]["code"]
        if len(matches) > 1:
            raise TermAmbiguousError(term_set, value, matches, param_name)
        available_entries = self.get_entries(term_set, dataset_id, term_type_code, keyword or "")
        raise TermNotFoundError(term_set, value, None, param_name, available_entries)

    def resolve_value(
        self,
        term_set: str,
        value: str,
        term_field: str | None = None,
        dataset_id: int | None = None,
        term_type_code: str | None = None,
        keyword: str | None = None,
        param_name: str | None = None,
    ) -> str:
        """根据 term_field 解析为 code 或 label。term_field 为 'code' 时返回 code，为 'name' 时返回 label。"""
        if term_field == "name":
            memory_matches: list[dict[str, str]] = []
            for entry in self._mapping_entries(term_set):
                if value in (entry.code, entry.label, *entry.aliases):
                    memory_matches.append({"code": entry.code, "label": entry.label})
            if len(memory_matches) == 1:
                return memory_matches[0]["label"]
            if len(memory_matches) > 1:
                raise TermAmbiguousError(term_set, value, memory_matches, param_name)

            tc = self._resolve_term_type_code(term_set, term_type_code)
            search_keyword = keyword or value
            cached = self._get_cached_entries(tc, search_keyword)
            matches: list[dict[str, str]] = []
            for entry in cached:
                if value in (entry.code, entry.label, *entry.aliases):
                    matches.append({"code": entry.code, "label": entry.label})
            if len(matches) == 1:
                return matches[0]["label"]
            if len(matches) > 1:
                raise TermAmbiguousError(term_set, value, matches, param_name)
            available_entries = self.get_entries(
                term_set, dataset_id, term_type_code, keyword or ""
            )
            raise TermNotFoundError(term_set, value, None, param_name, available_entries)
        return self.resolve_code(term_set, value, dataset_id, term_type_code, keyword, param_name)

    def get_available_values(
        self,
        term_set: str,
        dataset_id: int | None = None,
        term_type_code: str | None = None,
        keyword: str = "",
    ) -> list[str]:
        """返回术语集的所有标签值。"""
        memory_entries = self._mapping_entries(term_set)
        if memory_entries:
            return [e.label for e in memory_entries]
        tc = self._resolve_term_type_code(term_set, term_type_code)
        entries = self._get_cached_entries(tc, keyword)
        return [e.label for e in entries]

    def get_codes(
        self,
        term_set: str,
        dataset_id: int | None = None,
        term_type_code: str | None = None,
    ) -> list[str]:
        """返回术语集的所有 code 值。"""
        memory_entries = self._mapping_entries(term_set)
        if memory_entries:
            return [e.code for e in memory_entries]
        tc = self._resolve_term_type_code(term_set, term_type_code)
        entries = self._get_cached_entries(tc, "")
        return [e.code for e in entries]

    def get_entries(
        self,
        term_set: str,
        dataset_id: int | None = None,
        term_type_code: str | None = None,
        keyword: str = "",
    ) -> list[dict[str, str]]:
        """返回术语集的所有条目，每项包含 code 和 label。"""
        memory_entries = self._mapping_entries(term_set)
        if memory_entries:
            return [{"code": e.code, "label": e.label} for e in memory_entries]
        tc = self._resolve_term_type_code(term_set, term_type_code)
        entries = self._get_cached_entries(tc, keyword)
        return [{"code": e.code, "label": e.label} for e in entries]
