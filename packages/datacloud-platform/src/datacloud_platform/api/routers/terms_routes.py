"""Term option APIs for frontend form controls."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from datacloud_platform.loader_runtime import get_request_loader_snapshot

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Terms"])

_DEFAULT_PAGE = 1
_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100


class TermOptionItem(BaseModel):
    """A selectable term option."""

    label: str
    value: str
    code: str = ""
    name: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class TermOptionsData(BaseModel):
    """Paginated term options payload."""

    model_config = ConfigDict(populate_by_name=True)

    items: list[TermOptionItem] = Field(default_factory=list)
    page: int = _DEFAULT_PAGE
    page_size: int = Field(default=_DEFAULT_PAGE_SIZE, alias="pageSize")
    total: int = 0
    has_more: bool = Field(default=False, alias="hasMore")


class TermOptionsResponse(BaseModel):
    """Unified response wrapper for term options."""

    code: int = 0
    message: str = "success"
    data: TermOptionsData | None = None


class TermOptionsRequest(BaseModel):
    """Request body for term option lookup."""

    model_config = ConfigDict(populate_by_name=True)

    term_set: str = Field(default="", alias="termSet")
    term_type_code: str = Field(default="", alias="termTypeCode")
    term_field: str | None = Field(default="", alias="termField")
    dataset_id: int | None = Field(default=None, alias="datasetId")
    keyword: str = ""
    page: int = _DEFAULT_PAGE
    page_size: int = Field(default=_DEFAULT_PAGE_SIZE, alias="pageSize")


@router.post("/datacloud/terms/options", response_model=TermOptionsResponse)
async def term_options_endpoint(
    body: TermOptionsRequest,
    request: Request,
    response: Response,
) -> TermOptionsResponse:
    """Return paginated term options for operation confirmation forms."""
    term_set = body.term_set.strip()
    term_type_code = body.term_type_code.strip()
    if not term_set:
        response.status_code = 400
        return TermOptionsResponse(code=400, message="termSet is required", data=None)
    if not term_type_code:
        response.status_code = 400
        return TermOptionsResponse(
            code=400, message="termTypeCode is required", data=None
        )

    normalized_page = max(body.page, _DEFAULT_PAGE)
    normalized_page_size = min(max(body.page_size, 1), _MAX_PAGE_SIZE)
    if body.term_field is None:
        body.term_field = ""
    term_field = body.term_field.strip().lower()
    search_keyword = body.keyword.strip()
    offset = (normalized_page - 1) * normalized_page_size

    snapshot = await get_request_loader_snapshot(request, reason="term_options")
    loader = snapshot.loader if snapshot is not None else None
    term_loader = getattr(getattr(loader, "_config", None), "term_loader", None)
    if term_loader is None:
        logger.warning("term options requested but term_loader is not configured")
        return TermOptionsResponse(
            data=TermOptionsData(
                items=[],
                page=normalized_page,
                pageSize=normalized_page_size,
                total=0,
                hasMore=False,
            )
        )

    try:
        raw_entries, total = term_loader.get_entries_page(
            term_set,
            dataset_id=body.dataset_id,
            term_type_code=term_type_code,
            keyword=search_keyword,
            limit=normalized_page_size,
            offset=offset,
        )
        raw_entries = list(raw_entries or [])
    except AttributeError:
        try:
            all_entries = list(
                term_loader.get_entries(
                    term_set,
                    dataset_id=body.dataset_id,
                    term_type_code=term_type_code,
                    keyword=search_keyword,
                )
                or []
            )
        except Exception as exc:
            return _term_options_error_response(
                response,
                exc,
                term_set=term_set,
                term_type_code=term_type_code,
            )
        total = len(all_entries)
        raw_entries = all_entries[offset : offset + normalized_page_size]
    except Exception as exc:
        return _term_options_error_response(
            response,
            exc,
            term_set=term_set,
            term_type_code=term_type_code,
        )

    items = [
        _build_option_item(entry, term_field=term_field)
        for entry in raw_entries
        if isinstance(entry, dict)
    ]
    return TermOptionsResponse(
        data=TermOptionsData(
            items=items,
            page=normalized_page,
            pageSize=normalized_page_size,
            total=total,
            hasMore=offset + normalized_page_size < total,
        )
    )


def _term_options_error_response(
    response: Response,
    exc: Exception,
    *,
    term_set: str,
    term_type_code: str,
) -> TermOptionsResponse:
    logger.exception(
        "failed to load term options: term_set=%s term_type_code=%s",
        term_set,
        term_type_code,
    )
    response.status_code = 500
    return TermOptionsResponse(code=500, message=str(exc), data=None)


def _build_option_item(entry: dict[str, Any], *, term_field: str) -> TermOptionItem:
    code = str(entry.get("code") or entry.get("value") or "").strip()
    name = str(entry.get("name") or entry.get("label") or "").strip()
    label = str(entry.get("label") or name or code).strip()
    value = name if term_field == "name" else code
    if not value:
        value = label
    metadata = entry.get("metadata")
    return TermOptionItem(
        label=label,
        value=value,
        code=code,
        name=name,
        metadata=metadata if isinstance(metadata, dict) else {},
    )
