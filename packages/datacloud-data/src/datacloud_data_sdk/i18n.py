"""Lightweight i18n helpers for DataCloud SDK runtime messages."""

from __future__ import annotations

from typing import Final

DEFAULT_LANGUAGE: Final[str] = "zh-CN"
SUPPORTED_LANGUAGES: Final[frozenset[str]] = frozenset({"zh-CN", "en_US"})

_LANGUAGE_ALIASES: Final[dict[str, str]] = {
    "zh": "zh-CN",
    "zh_cn": "zh-CN",
    "zh-cn": "zh-CN",
    "cn": "zh-CN",
    "chinese": "zh-CN",
    "en": "en_US",
    "en_us": "en_US",
    "en-us": "en_US",
    "english": "en_US",
}


def normalize_language(language: str | None) -> str:
    """Normalize language aliases to supported DataCloud language codes."""
    raw = str(language or "").strip()
    if not raw:
        return DEFAULT_LANGUAGE
    first_token = raw.split(",", 1)[0].split(";", 1)[0].strip()
    if not first_token:
        return DEFAULT_LANGUAGE
    raw = first_token
    if raw in SUPPORTED_LANGUAGES:
        return raw
    return _LANGUAGE_ALIASES.get(raw.lower(), DEFAULT_LANGUAGE)


def is_english(language: str | None) -> bool:
    """Return whether the normalized language is English."""
    return normalize_language(language) == "en_US"


def localized_text(language: str | None, *, zh_cn: str, en_us: str) -> str:
    """Select localized text by language."""
    return en_us if is_english(language) else zh_cn


def format_overflow_notice(
    *,
    language: str | None,
    total: int,
    preview_count: int,
    file_path: str | None = None,
    download_url: str | None = None,
) -> str:
    """Build a localized large-result notice."""
    if download_url:
        return localized_text(
            language,
            zh_cn=(
                f"【重要】数据量较大（共 {total} 条），此处仅返回前 {preview_count} 条预览。"
                f"完整数据请通过以下地址下载 CSV：{download_url}"
            ),
            en_us=(
                f"Important: the result is large ({total} rows). "
                f"Only the first {preview_count} rows are returned here. "
                f"Download the full CSV here: {download_url}"
            ),
        )

    resolved_path = file_path or ""
    return localized_text(
        language,
        zh_cn=(
            f"【重要】数据量较大（共 {total} 条），此处仅返回前 {preview_count} 条预览。"
            f"完整数据请通过以下文件路径获取：{resolved_path}"
        ),
        en_us=(
            f"Important: the result is large ({total} rows). "
            f"Only the first {preview_count} rows are returned here. "
            f"Read the full data from this file path: {resolved_path}"
        ),
    )
