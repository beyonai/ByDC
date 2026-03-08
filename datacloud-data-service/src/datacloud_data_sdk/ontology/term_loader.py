"""术语集加载与解析：code / label / aliases 多维匹配。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TermEntry:
    code: str
    label: str
    aliases: list[str] = field(default_factory=list)


class TermLoader:
    """术语集加载器，支持 code、label、alias 三种匹配方式。"""

    def __init__(self) -> None:
        self._sets: dict[str, list[TermEntry]] = {}

    @classmethod
    def from_mapping(cls, mapping: dict[str, list[dict[str, object]]]) -> TermLoader:
        loader = cls()
        for term_set, entries in mapping.items():
            loader._sets[term_set] = [
                TermEntry(
                    code=str(e["code"]),
                    label=str(e["label"]),
                    aliases=[str(a) for a in e.get("aliases", [])],  # type: ignore[union-attr]
                )
                for e in entries
            ]
        return loader

    def resolve_code(self, term_set: str, value: str) -> str:
        """将标签/别名/code 解析为标准 code。"""
        for entry in self._sets.get(term_set, []):
            if value in (entry.code, entry.label, *entry.aliases):
                return entry.code
        available = self.get_available_values(term_set)
        raise ValueError(
            f"Unknown term {value!r} in {term_set!r}. available: {available}"
        )

    def get_available_values(self, term_set: str) -> list[str]:
        """返回术语集的所有标签值。"""
        return [e.label for e in self._sets.get(term_set, [])]
