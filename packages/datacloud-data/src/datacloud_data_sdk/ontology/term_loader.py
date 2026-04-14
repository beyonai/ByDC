"""术语集加载与解析：code / label / aliases 多维匹配。"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from datacloud_data_sdk.exceptions import TermAmbiguousError, TermNotFoundError

try:
    from datacloud_knowledge.knowledge_search.term_search import search_terms_by_type
except ImportError:
    search_terms_by_type = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


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
        """根据配置返回 ApiTermLoader 或 KbTermLoader。

        config 留空时直接从环境变量读取：
        - DATACLOUD_TERM_LOADER_TYPE: api | kb（默认 kb）
        - DATACLOUD_ZNT_SERVER: ApiTermLoader 的 base_url
        """
        import os

        loader_type = config.get("type", os.environ.get("DATACLOUD_TERM_LOADER_TYPE", "kb"))
        if loader_type == "api":
            base_url = config.get("base_url", os.environ.get("DATACLOUD_ZNT_SERVER", ""))
            return ApiTermLoader.from_config({"base_url": base_url})
        return KbTermLoader.from_config(config.get("kb", {}))

    @classmethod
    def from_mapping(cls, mapping: dict[str, list[dict[str, object]]]) -> TermLoader:
        """兼容原有接口，返回 ApiTermLoader（内存 mapping 模式）。"""
        return ApiTermLoader(mapping=mapping)


class ApiTermLoader(TermLoader):
    """基于远程 API 的术语加载器。"""

    def __init__(
        self,
        mapping: dict[str, list[dict[str, object]]] | None = None,
        api_base_url: str | None = None,
    ) -> None:
        self._sets: dict[str, list[TermEntry]] = {}
        self._api_base_url = api_base_url or ""
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

    def configure_api(self, base_url: str) -> None:
        """配置术语 API 基础地址。"""
        self._api_base_url = base_url.rstrip("/") if base_url else ""

    @classmethod
    def from_config(cls, config: dict) -> ApiTermLoader:
        return cls(
            mapping=config.get("mapping"),
            api_base_url=config.get("base_url"),
        )

    def _fetch_from_api(
        self,
        dataset_id: int,
        term_type_code: str,
        keyword: str = "",
    ) -> list[TermEntry]:
        """调用术语 API 获取术语列表。"""
        if not self._api_base_url:
            return []
        try:
            import httpx

            from datacloud_data_sdk.utils.curl_logger import log_curl

            url = f"{self._api_base_url}/core/term/queryStandardTerm"
            body: dict[str, Any] = {
                "datasetIds": [str(dataset_id)],
                "termType": term_type_code,
                "keyword": keyword or "",
                "queryType": "fullTextRecall",
                "topK": 100,
            }
            headers = {
                "beyond-token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJjb21BY2N0SWQiOjEsImxvZ2luVHlwZSI6InVzZXJuYW1lIiwic2Vzc2lvbklkIjoiNmI5N2ZmZTgtYmYxYy00YWQzLWE4ZmEtMzBlMzExZGEwNTc1IiwidXNlck5hbWUiOiJhZG1pbnZpcCIsInVzZXJJZCI6NywidXNlckNvZGUiOiJhZG1pbnZpcCIsInVzZXJzT3JnYW5pemF0aW9ucyI6W3sicGF0aE5hbWUiOiLmtanpsrjnp5HmioAo5LiA57qn57uP6JCl5aeU5ZGY5LyaKS3mgLvnu4_nkIblip7lhazlrqQiLCJwb3NpdGlvbk5hbWUiOiJJVOi_kOe7tOW3peeoi-W4iCIsIm9yZ05hbWUiOiLmgLvnu4_nkIblip7lhazlrqQiLCJwb3NpdGlvbklkIjoxMDM1LCJwYXRoQ29kZSI6Ii0xLjQwMC43NTIiLCJ1c2VyVHlwZSI6Ik9SR19NQU4iLCJvcmdJZCI6NzUyfSx7InBhdGhOYW1lIjoi5rWp6bK456eR5oqAKOS4gOe6p-e7j-iQpeWnlOWRmOS8mikt5oC757uP55CG5Yqe5YWs5a6kIiwicG9zaXRpb25OYW1lIjoiSVTov5Dnu7Tlt6XnqIvluIgiLCJvcmdOYW1lIjoi5oC757uP55CG5Yqe5YWs5a6kIiwicG9zaXRpb25JZCI6MTAzNSwicGF0aENvZGUiOiItMS40MDAuNzUyIiwidXNlclR5cGUiOiJQTEFUX01BTiIsIm9yZ0lkIjo3NTJ9LHsicGF0aE5hbWUiOiLmtanpsrjnp5HmioAo5LiA57qn57uP6JCl5aeU5ZGY5LyaKS3mlbDmja7mmbrog73kuqflk4Hnur8t5YWx5Lqr5bmz5Y-w5Lit5b-DLeeZvuW6lOS6pOS7mOWboumYny3nmb7lupTluILlnLrpg6giLCJwb3NpdGlvbk5hbWUiOiLlrp7kuaDnlJ8iLCJvcmdOYW1lIjoi55m-5bqU5Lqk5LuY5Zui6ZifIiwicG9zaXRpb25JZCI6MTMxMywicGF0aENvZGUiOiItMS40MDAuMjczNy4yNzQ0Ljc4NDQuNzg0NyIsInVzZXJUeXBlIjoiQlVTSU5FU1NfTUFOIiwib3JnSWQiOjc4NDd9LHsicGF0aE5hbWUiOiLmtanpsrjnp5HmioAo5LiA57qn57uP6JCl5aeU5ZGY5LyaKSIsInBvc2l0aW9uTmFtZSI6IklU6L-Q57u05bel56iL5biIIiwib3JnTmFtZSI6Iua1qemyuOenkeaKgCjkuIDnuqfnu4_okKXlp5TlkZjkvJopIiwicG9zaXRpb25JZCI6MTAzNSwicGF0aENvZGUiOiItMS40MDAiLCJ1c2VyVHlwZSI6IlBMQVRfTUFOIiwib3JnSWQiOjQwMH0seyJwYXRoTmFtZSI6Iua1qemyuOenkeaKgCjkuIDnuqfnu4_okKXlp5TlkZjkvJopIiwicG9zaXRpb25OYW1lIjoiSVTov5Dnu7Tlt6XnqIvluIgiLCJvcmdOYW1lIjoi5rWp6bK456eR5oqAKOS4gOe6p-e7j-iQpeWnlOWRmOS8mikiLCJwb3NpdGlvbklkIjoxMDM1LCJwYXRoQ29kZSI6Ii0xLjQwMCIsInVzZXJUeXBlIjoiT1JHX01BTiIsIm9yZ0lkIjo0MDB9LHsicGF0aE5hbWUiOiLmtanpsrjnp5HmioAo5LiA57qn57uP6JCl5aeU5ZGY5LyaKS3mlbDmja7mmbrog73kuqflk4Hnur8t5YWx5Lqr5bmz5Y-w5Lit5b-DLeeZvuW6lOS6pOS7mOWboumYny3nmb7lupTluILlnLrpg6giLCJwb3NpdGlvbk5hbWUiOiLlrp7kuaDnlJ8iLCJvcmdOYW1lIjoi55m-5bqU5Lqk5LuY5Zui6ZifIiwicG9zaXRpb25JZCI6MTMxMywicGF0aENvZGUiOiItMS40MDAuMjczNy4yNzQ0Ljc4NDQuNzg0NyIsInVzZXJUeXBlIjoiQlVTSU5FU1NfTUFOIiwib3JnSWQiOjc4NDd9LHsicGF0aE5hbWUiOiLmtanpsrjnp5HmioAo5LiA57qn57uP6JCl5aeU5ZGY5LyaKS3mlbDmja7mmbrog73kuqflk4Hnur8t5YWx5Lqr5bmz5Y-w5Lit5b-DLeeZvuW6lOS6pOS7mOWboumYny3nmb7lupTluILlnLrpg6giLCJwb3NpdGlvbk5hbWUiOiLlrp7kuaDnlJ8iLCJvcmdOYW1lIjoi55m-5bqU5Lqk5LuY5Zui6ZifIiwicG9zaXRpb25JZCI6MTMxMywicGF0aENvZGUiOiItMS40MDAuMjczNy4yNzQ0Ljc4NDQuNzg0NyIsInVzZXJUeXBlIjoiQlVTSU5FU1NfTUFOIiwib3JnSWQiOjc4NDd9XSwiYWNjb3VudEFjY3RpZCI6MSwic2Vzc2lvblR5cGUiOiJzeW5jIn0iLCJjb2RpbmciOiJBbGciLCJjb21BY2N0SWQiOjEsInVzZXJJZCI6NywidXNlck5hbWUiOiJhZG1pbnZpcCIsInVzZXJJZCI6NywidXNlckNvZGUiOiJhZG1pbnZpcCIsImFjdGl2ZUFjY291bnQiOiIxIiwiYWNjb3VudEFjY3RpZCI6MSwiaWF0IjoxNzczNzQyNjI3fQ.eyJjb2RpbmciOiJBbGciLCJjb21BY2N0SWQiOjEsInVzZXJJZCI6NywidXNlck5hbWUiOiJhZG1pbnZpcCIsInVzZXJJZCI6NywidXNlckNvZGUiOiJhZG1pbnZpcCIsImFjdGl2ZUFjY291bnQiOiIxIiwiYWNjb3VudEFjY3RpZCI6MSwiaWF0IjoxNzczNzQyNjI3fQ.Wr3limrS1ppnKd56MCRK01v5lzl3N1IX_bchkgKipyk",
                "sso-token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6NywiY29kZSI6ImFkbWludmlwIiwibmFtZSI6ImFkbWludmlwIiwiZW1haWwiOiJhZG1pbnZpcEBieWFpLmNvbSIsInBob25lIjoiVHZ2anpMekU2K0pVc2pHVmh3N3lYdz09IiwiZXhwIjoxNzczNzQzMjEyfQ.L6uLo9TujvG11a1CYJZNz31_CLnZNh25z7DS7FIyHpU",
                "cookie": "uc=adminvip; PORTAL-SESSION=6b97ffe8-bf1c-4ad3-a8fa-30e311da0575; SESSION=6b97ffe8-bf1c-4ad3-a8fa-30e311da0575; undefined=",
                "system-code": "BYAI",
            }
            log_curl("POST", url, headers=headers, body=body)
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(url, json=body, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except ImportError:
            logger.warning("httpx not installed, cannot call term API")
            return []
        except Exception as e:
            logger.warning("Term API call failed: %s", e)
            return []

        result_obj = data.get("resultObject") or {}
        raw_list = (
            result_obj.get("termInfoList") or data.get("termInfoList") or data.get("data") or []
        )
        if not isinstance(raw_list, list):
            raw_list = []

        entries: list[TermEntry] = []
        for item in raw_list:
            code = item.get("termCode", item.get("code", ""))
            label = item.get("termName", item.get("label", ""))
            syn = item.get("synonyms", "")
            aliases = [s.strip() for s in str(syn).split(",") if s.strip()] if syn else []
            if code or label:
                entries.append(TermEntry(code=str(code), label=str(label), aliases=aliases))
        return entries

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
        matches: list[dict[str, str]] = []
        for entry in self._sets.get(term_set, []):
            if value in (entry.code, entry.label, *entry.aliases):
                matches.append(
                    {
                        "code": entry.code,
                        "label": entry.label,
                        "aliases": entry.aliases,
                    }
                )
        if len(matches) == 1:
            return matches[0]["code"]
        if len(matches) > 1:
            raise TermAmbiguousError(term_set, value, matches, param_name)
        if self._api_base_url and dataset_id and (term_type_code or "." in term_set):
            tc = term_type_code or term_set.split(".")[0]
            entries = self._fetch_from_api(dataset_id, tc, keyword=keyword or value)
            api_matches: list[dict[str, str]] = []
            for entry in entries:
                if value in (entry.code, entry.label, *entry.aliases):
                    api_matches.append(
                        {
                            "code": entry.code,
                            "label": entry.label,
                            "aliases": entry.aliases,
                        }
                    )
            if len(api_matches) == 1:
                return api_matches[0]["code"]
            if len(api_matches) > 1:
                raise TermAmbiguousError(term_set, value, api_matches, param_name)
        available_entries = self.get_entries(
            term_set, dataset_id=dataset_id, term_type_code=term_type_code
        )
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
            matches: list[dict[str, str]] = []
            for entry in self._sets.get(term_set, []):
                if value in (entry.code, entry.label, *entry.aliases):
                    matches.append(
                        {
                            "code": entry.code,
                            "label": entry.label,
                            "aliases": entry.aliases,
                        }
                    )
            if len(matches) == 1:
                return matches[0]["label"]
            if len(matches) > 1:
                raise TermAmbiguousError(term_set, value, matches, param_name)
            if self._api_base_url and dataset_id and (term_type_code or "." in term_set):
                tc = term_type_code or term_set.split(".")[0]
                entries = self._fetch_from_api(dataset_id, tc, keyword=keyword or value)
                api_matches: list[dict[str, str]] = []
                for entry in entries:
                    if value in (entry.code, entry.label, *entry.aliases):
                        api_matches.append(
                            {
                                "code": entry.code,
                                "label": entry.label,
                                "aliases": entry.aliases,
                            }
                        )
                if len(api_matches) == 1:
                    return api_matches[0]["label"]
                if len(api_matches) > 1:
                    raise TermAmbiguousError(term_set, value, api_matches, param_name)
            available_entries = self.get_entries(
                term_set, dataset_id=dataset_id, term_type_code=term_type_code
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
        """返回术语集的所有标签值。API 模式下需 dataset_id。"""
        mem = self._sets.get(term_set, [])
        if mem:
            return [e.label for e in mem]
        if self._api_base_url and dataset_id and (term_type_code or "." in term_set):
            tc = term_type_code or term_set.split(".")[0]
            entries = self._fetch_from_api(dataset_id, tc, keyword=keyword)
            return [e.label for e in entries]
        return []

    def get_codes(
        self,
        term_set: str,
        dataset_id: int | None = None,
        term_type_code: str | None = None,
    ) -> list[str]:
        """返回术语集的所有 code 值，用于 schema enum。内存模式直接返回；API 模式需 dataset_id。"""
        mem = self._sets.get(term_set, [])
        if mem:
            return [e.code for e in mem]
        if self._api_base_url and dataset_id and (term_type_code or "." in term_set):
            tc = term_type_code or term_set.split(".")[0]
            entries = self._fetch_from_api(dataset_id, tc, keyword="")
            return [e.code for e in entries]
        return []

    def get_entries(
        self,
        term_set: str,
        dataset_id: int | None = None,
        term_type_code: str | None = None,
        keyword: str = "",
    ) -> list[dict[str, str]]:
        """返回术语集的所有条目，每项包含 code 和 label。"""
        mem = self._sets.get(term_set, [])
        if mem:
            return [{"code": e.code, "label": e.label} for e in mem]
        if self._api_base_url and dataset_id and (term_type_code or "." in term_set):
            tc = term_type_code or term_set.split(".")[0]
            entries = self._fetch_from_api(dataset_id, tc, keyword=keyword)
            return [{"code": e.code, "label": e.label} for e in entries]
        return []


class KbTermLoader(TermLoader):
    """基于 knowledge_search 的术语加载器。"""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], list[TermEntry]] = {}

    @classmethod
    def from_config(cls, config: dict) -> KbTermLoader:
        return cls()

    def _resolve_term_type_code(self, term_set: str, term_type_code: str | None) -> str:
        if term_type_code:
            return term_type_code
        if "." in term_set:
            return term_set.split(".")[0]
        return term_set

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
        if cached is None:
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
        tc = self._resolve_term_type_code(term_set, term_type_code)
        search_keyword = keyword or value
        cached = self._get_cached_entries(tc, search_keyword)
        matches: list[dict[str, str]] = []
        for entry in cached:
            if value in (entry.code, entry.label, *entry.aliases):
                matches.append(
                    {
                        "code": entry.code,
                        "label": entry.label,
                        "aliases": entry.aliases,
                    }
                )
        if len(matches) == 1:
            return matches[0]["code"]
        if len(matches) > 1:
            raise TermAmbiguousError(term_set, value, matches, param_name)
        available_entries = self.get_entries(term_set, dataset_id, term_type_code, keyword)
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
            tc = self._resolve_term_type_code(term_set, term_type_code)
            search_keyword = keyword or value
            cached = self._get_cached_entries(tc, search_keyword)
            matches: list[dict[str, str]] = []
            for entry in cached:
                if value in (entry.code, entry.label, *entry.aliases):
                    matches.append(
                        {
                            "code": entry.code,
                            "label": entry.label,
                            "aliases": entry.aliases,
                        }
                    )
            if len(matches) == 1:
                return matches[0]["label"]
            if len(matches) > 1:
                raise TermAmbiguousError(term_set, value, matches, param_name)
            available_entries = self.get_entries(term_set, dataset_id, term_type_code, keyword)
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
        tc = self._resolve_term_type_code(term_set, term_type_code)
        entries = self._search(tc, keyword=keyword)
        return [e.label for e in entries]

    def get_codes(
        self,
        term_set: str,
        dataset_id: int | None = None,
        term_type_code: str | None = None,
    ) -> list[str]:
        """返回术语集的所有 code 值。"""
        tc = self._resolve_term_type_code(term_set, term_type_code)
        entries = self._search(tc, keyword="")
        return [e.code for e in entries]

    def get_entries(
        self,
        term_set: str,
        dataset_id: int | None = None,
        term_type_code: str | None = None,
        keyword: str = "",
    ) -> list[dict[str, str]]:
        """返回术语集的所有条目，每项包含 code 和 label。"""
        tc = self._resolve_term_type_code(term_set, term_type_code)
        entries = self._search(tc, keyword=keyword)
        return [{"code": e.code, "label": e.label} for e in entries]
