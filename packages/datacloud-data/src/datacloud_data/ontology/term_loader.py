"""术语集加载与解析：code / label / aliases 多维匹配。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TermEntry:
    code: str
    label: str
    aliases: list[str] = field(default_factory=list)


class TermLoader:
    """术语集加载器，支持内存 mapping 与 API 模式。"""

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
    def from_mapping(cls, mapping: dict[str, list[dict[str, object]]]) -> TermLoader:
        loader = cls(mapping=mapping)
        return loader

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

            from datacloud_data.utils.curl_logger import log_curl

            url = f"{self._api_base_url}/core/term/queryStandardTerm"
            body: dict[str, Any] = {
                "datasetIds": [str(dataset_id)],
                "termType": term_type_code,
                "keyword": keyword or "",
                "queryType": "fullTextRecall",
                "topK": 100,
            }
            headers = {
                "beyond-token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJjb21BY2N0SWQiOjEsImxvZ2luVHlwZSI6InVzZXJuYW1lIiwic2Vzc2lvbklkIjoiNmI5N2ZmZTgtYmYxYy00YWQzLWE4ZmEtMzBlMzExZGEwNTc1IiwidXNlck5hbWUiOiJhZG1pbnZpcCIsInVzZXJJZCI6NywidXNlckNvZGUiOiJhZG1pbnZpcCIsInVzZXJzT3JnYW5pemF0aW9ucyI6W3sicGF0aE5hbWUiOiLmtanpsrjnp5HmioAo5LiA57qn57uP6JCl5aeU5ZGY5LyaKS3mgLvnu4_nkIblip7lhazlrqQiLCJwb3NpdGlvbk5hbWUiOiJJVOi_kOe7tOW3peeoi-W4iCIsIm9yZ05hbWUiOiLmgLvnu4_nkIblip7lhazlrqQiLCJwb3NpdGlvbklkIjoxMDM1LCJwYXRoQ29kZSI6Ii0xLjQwMC43NTIiLCJ1c2VyVHlwZSI6Ik9SR19NQU4iLCJvcmdJZCI6NzUyfSx7InBhdGhOYW1lIjoi5rWp6bK456eR5oqAKOS4gOe6p-e7j-iQpeWnlOWRmOS8mikt5oC757uP55CG5Yqe5YWs5a6kIiwicG9zaXRpb25OYW1lIjoiSVTov5Dnu7Tlt6XnqIvluIgiLCJvcmdOYW1lIjoi5oC757uP55CG5Yqe5YWs5a6kIiwicG9zaXRpb25JZCI6MTAzNSwicGF0aENvZGUiOiItMS40MDAuNzUyIiwidXNlclR5cGUiOiJQTEFUX01BTiIsIm9yZ0lkIjo3NTJ9LHsicGF0aE5hbWUiOiLmtanpsrjnp5HmioAo5LiA57qn57uP6JCl5aeU5ZGY5LyaKS3mlbDmja7mmbrog73kuqflk4Hnur8t5YWx5Lqr5bmz5Y-w5Lit5b-DLeeZvuW6lOS6pOS7mOWboumYny3nmb7lupTluILlnLrpg6giLCJwb3NpdGlvbk5hbWUiOiLlrp7kuaDnlJ8iLCJvcmdOYW1lIjoi55m-5bqU5Lqk5LuY5Zui6ZifIiwicG9zaXRpb25JZCI6MTMxMywicGF0aENvZGUiOiItMS40MDAuMjczNy4yNzQ0Ljc4NDQuNzg0NyIsInVzZXJUeXBlIjoiQlVTSU5FU1NfTUFOIiwib3JnSWQiOjc4NDd9LHsicGF0aE5hbWUiOiLmtanpsrjnp5HmioAo5LiA57qn57uP6JCl5aeU5ZGY5LyaKSIsInBvc2l0aW9uTmFtZSI6IklU6L-Q57u05bel56iL5biIIiwib3JnTmFtZSI6Iua1qemyuOenkeaKgCjkuIDnuqfnu4_okKXlp5TlkZjkvJopIiwicG9zaXRpb25JZCI6MTAzNSwicGF0aENvZGUiOiItMS40MDAiLCJ1c2VyVHlwZSI6IlBMQVRfTUFOIiwib3JnSWQiOjQwMH0seyJwYXRoTmFtZSI6Iua1qemyuOenkeaKgCjkuIDnuqfnu4_okKXlp5TlkZjkvJopIiwicG9zaXRpb25OYW1lIjoiSVTov5Dnu7Tlt6XnqIvluIgiLCJvcmdOYW1lIjoi5rWp6bK456eR5oqAKOS4gOe6p-e7j-iQpeWnlOWRmOS8mikiLCJwb3NpdGlvbklkIjoxMDM1LCJwYXRoQ29kZSI6Ii0xLjQwMCIsInVzZXJUeXBlIjoiT1JHX01BTiIsIm9yZ0lkIjo0MDB9LHsicGF0aE5hbWUiOiLmtanpsrjnp5HmioAo5LiA57qn57uP6JCl5aeU5ZGY5LyaKS3mlbDmja7mmbrog73kuqflk4Hnur8t5YWx5Lqr5bmz5Y-w5Lit5b-DLeeZvuW6lOS6pOS7mOWboumYny3nmb7lupTluILlnLrpg6giLCJwb3NpdGlvbk5hbWUiOiLlrp7kuaDnlJ8iLCJvcmdOYW1lIjoi55m-5bqU5Lqk5LuY5Zui6ZifIiwicG9zaXRpb25JZCI6MTMxMywicGF0aENvZGUiOiItMS40MDAuMjczNy4yNzQ0Ljc4NDQuNzg0NyIsInVzZXJUeXBlIjoiREVWX1VTRVIiLCJvcmdJZCI6Nzg0N30seyJwYXRoTmFtZSI6IuS6p-WTgeS6i-S4mumDqC3mtanpsrjnp5HmioAo5LiA57qn57uP6JCl5aeU5ZGY5LyaKS3kuqflk4HlhbHkuqvkuK3lv4Mt5Zu95YaF5Lia5Yqh6L-Q6JCl5Lit5b-DLeS6p-WTgeeglOWPkeS6jOmDqC3kuqflk4HnoJTlj5Hkuozpg6jnrKzkuozlm6LpmJ8iLCJwb3NpdGlvbk5hbWUiOiJCVeaAu-e7j-eQhiIsIm9yZ05hbWUiOiLkuqflk4HnoJTlj5Hkuozpg6jnrKzkuozlm6LpmJ8iLCJwb3NpdGlvbklkIjoxMDgzLCJwYXRoQ29kZSI6Ii0xLjQwMC40MDIuNzA3NS42MDgxLjc4MjguNzgzMyIsInVzZXJUeXBlIjoiUExBVF9NQU4iLCJvcmdJZCI6NzgzM30seyJwYXRoTmFtZSI6IuS6p-WTgeS6i-S4mumDqC3mtanpsrjnp5HmioAo5LiA57qn57uP6JCl5aeU5ZGY5LyaKS3kuqflk4HlhbHkuqvkuK3lv4Mt5Zu95YaF5Lia5Yqh6L-Q6JCl5Lit5b-DLeS6p-WTgeeglOWPkeS6jOmDqC3kuqflk4HnoJTlj5Hkuozpg6jnrKzkuozlm6LpmJ8iLCJwb3NpdGlvbk5hbWUiOiJCVeaAu-e7j-eQhiIsIm9yZ05hbWUiOiLkuqflk4HnoJTlj5Hkuozpg6jnrKzkuozlm6LpmJ8iLCJwb3NpdGlvbklkIjoxMDgzLCJwYXRoQ29kZSI6Ii0xLjQwMC40MDIuNzA3NS42MDgxLjc4MjguNzgzMyIsInVzZXJUeXBlIjoiQlVTSU5FU1NfTUFOIiwib3JnSWQiOjc4MzN9XSwiYXNzaXN0YW50SWQiOjcsInBob25lIjoiVHZ2anpMekU2K0pVc2pHVmh3N3lYdz09IiwiaXNEZWZhdWx0UHdkIjpmYWxzZSwiZW50ZXJwcmlzZUlkIjoxLCJpc1JldGVudGVkIjpmYWxzZSwic2Vzc2lvbkRhdGFzZXRJZCI6IjE0NjAzNTE5MjYyNDkxMDc0NTYiLCJlbWFpbCI6ImFkbWludmlwQGJ5YWkuY29tIiwidXNlck1hbmFnZU9yZ3MiOltdLCJleHAiOjE3NzM3NDMyMTJ9.nBmbyKh40bpd-VsD657CjVImQ-KigNrWUVvntMQxIv2R_ZksTPOWkZALi7zhvsTEQOxffpf9rCPjdryS0Ry32qz-seMaLbGd7hB0nx0E_DHTIaz92g5EW3RNgGrb8oNxYajJqRjH21MEKlsqW96Benx0r77OIm9yCLfFsAwkC6-uhLapkhgOBJifSd5NUPfkseoaHJbOVab4JcdmRjSsG-3E6PfHI8QAh8r9rLQneAVapKI6qtYb2PqrRqrux7a-4deT954Dp710Xsk05jr4BopZu2IsAGu-UBihIH75CAHpWZWKHyZY5jg7MF1K9H14i8HhxfNeKNlNVW2sZ19xoQ",
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

        # 支持 resultObject.termInfoList 或顶层 termInfoList/data
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
    ) -> str:
        """将标签/别名/code 解析为标准 code。lookup 时可用 keyword=value 搜索。"""
        # 先查内存
        for entry in self._sets.get(term_set, []):
            if value in (entry.code, entry.label, *entry.aliases):
                return entry.code
        # API 模式：lookup 时用 keyword 搜索
        if self._api_base_url and dataset_id and (term_type_code or "." in term_set):
            tc = term_type_code or term_set.split(".")[0]
            entries = self._fetch_from_api(dataset_id, tc, keyword=keyword or value)
            for entry in entries:
                if value in (entry.code, entry.label, *entry.aliases):
                    return entry.code
            if entries:
                return entries[0].code
        available = self.get_available_values(
            term_set, dataset_id=dataset_id, term_type_code=term_type_code
        )
        raise ValueError(f"Unknown term {value!r} in {term_set!r}. available: {available}")

    def get_available_values(
        self,
        term_set: str,
        dataset_id: int | None = None,
        term_type_code: str | None = None,
        keyword: str = "",
    ) -> list[str]:
        """返回术语集的所有标签值。API 模式下需 dataset_id。"""
        # 内存优先
        mem = self._sets.get(term_set, [])
        if mem:
            return [e.label for e in mem]
        # API 模式
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
