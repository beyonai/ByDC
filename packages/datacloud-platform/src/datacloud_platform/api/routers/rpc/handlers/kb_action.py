"""RPC handlers for knowledge-base action execution.

Methods:
  - invokeAction: Execute a KB action (write_*, search_*, search_by_file_name_*,
    merge_write_*, delete_kb_*) via the ontology loader + execution backend pipeline.

This is the same path that OntologyLoader.invoke_action() uses internally:
  load_ontology → inject_virtual_actions → execute_action(loader, object_code, action_code, args)
"""

from __future__ import annotations

import json
import logging
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from fastapi import Request
from collections.abc import Mapping

from datacloud_platform.constants import DEFAULT_BASE_ID
from datacloud_platform.backends.document_library import DocumentLibraryError
from datacloud_platform.models.document import (
    DocumentAsyncProcessingAccepted,
    DocumentAsyncProcessingRequest,
    GetDocumentContentRequest,
    QueryDocumentObjectsRequest,
    QueryRelatedDocumentObjectsRequest,
    SearchDocumentFragmentsRequest,
)
from datacloud_platform.models.common import ok
from datacloud_platform.services.kb_document_reader import KbDocumentReadError
from datacloud_platform.services.object_action import invoke_object_action


from datacloud_platform.models.document import DocumentProcessingStatus
from datacloud_platform.mixins.document import build_processing_labels

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform

logger = logging.getLogger(__name__)


# ── invokeAction ──────────────────────────────────────────────────────────────


def prepare_action_arguments(
    *, action_code: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Add DataCloud processing labels to document write actions."""
    if not action_code.startswith("write_"):
        return arguments
    prepared = dict(arguments)
    raw_labels = prepared.get("labels")
    if raw_labels is not None and not isinstance(raw_labels, Mapping):
        raise ValueError("arguments.labels must be an object")
    prepared["labels"] = build_processing_labels(
        initial_status=DocumentProcessingStatus.PENDING_DISCOVERY,
        labels=raw_labels,
    )
    return prepared


async def _invoke_action(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    """Execute a KB action via ontology loader + execution backend.

    Mirrors the SDK call:
      loader.get_object(object_code).invoke_action(action_code, arguments)

    Params:
      - objectCode / object_code (str, required): Ontology object code.
      - actionCode / action_code (str, required): Action code to invoke,
          e.g. write_Ability, search_Ability, merge_write_Ability, delete_kb_Ability.
      - arguments (dict, optional): Action arguments forwarded verbatim
          to the execution backend. Common fields:
            - source_path (str): Document path, must start with /.
            - content (str): Markdown document body.
            - labels (dict): Metadata labels.
            - file_description (str): Human-readable file description.
            - query (str): Search query text (for search_* actions).
            - select (list[str]): Field list (for search_* actions).
            - filters (list): Filter conditions (for search_* actions).
            - limit (int): Max records (default depends on action).
    """
    object_code = str(params.get("object_code") or params.get("objectCode") or "")
    if not object_code:
        raise ValueError("object_code / objectCode is required")

    action_code = str(params.get("action_code") or params.get("actionCode") or "")
    if not action_code:
        raise ValueError("action_code / actionCode is required")

    arguments: dict[str, Any] = params.get("arguments") or {}
    base_id: str = str(params.get("base_id") or DEFAULT_BASE_ID)
    arguments = prepare_action_arguments(action_code=action_code, arguments=arguments)

    data = await invoke_object_action(
        platform=platform,
        base_id=base_id,
        object_code=object_code,
        action_code=action_code,
        arguments=arguments,
    )
    if action_code.startswith(("write_", "merge_write_")):
        session_id = _required_session_id(_req)
        object_detail = platform.get_object_detail(base_id, object_code)
        if object_detail is None:
            raise KeyError(f"object not found: {object_code}")
        resolved_object_code = str(
            object_detail.get("objectCode")
            or object_detail.get("object_code")
            or object_code
        )
        object_name = str(
            object_detail.get("objectName") or object_detail.get("object_name") or ""
        )
        if not object_name:
            raise KeyError(f"object name not found: {object_code}")
        source_path = str(arguments.get("source_path") or "")
        if not source_path:
            raise ValueError("arguments.source_path is required for write actions")
        labels = arguments.get("labels") or {}
        object_ext = object_detail.get("ext_property") or object_detail.get(
            "extProperty"
        )
        if not isinstance(object_ext, Mapping):
            object_ext = {}
        records = data.get("records")
        first_record = (
            records[0]
            if isinstance(records, list) and records and isinstance(records[0], Mapping)
            else {}
        )
        fallback_file_name = PurePosixPath(source_path).name
        file_name = str(
            first_record.get("fileName")
            or first_record.get("file_name")
            or fallback_file_name
        )
        kb_directory = str(
            object_ext.get("kb_directory") or object_ext.get("kbDirectory") or ""
        ).strip()
        if kb_directory and not kb_directory.startswith("/"):
            kb_directory = f"/{kb_directory}"
        fallback_directory = f"/{kb_directory.strip('/')}" if kb_directory else "/"
        fallback_file_path = (
            f"{fallback_directory.rstrip('/')}/{fallback_file_name}"
            if fallback_directory != "/"
            else f"/{fallback_file_name}"
        )
        file_path = str(
            first_record.get("filePath")
            or first_record.get("file_path")
            or fallback_file_path
        )
        await platform.save_or_update_object_files(
            base_id,
            object_files=[
                {
                    "sessionId": session_id,
                    "objectName": object_name,
                    "objectCode": resolved_object_code,
                    "fileName": file_name,
                    "filePath": file_path,
                    "version": str(labels.get("version") or "1"),
                    "statusCd": str(
                        labels.get("dc_status")
                        or DocumentProcessingStatus.PENDING_DISCOVERY.value
                    ),
                    "extContent": json.dumps(
                        {
                            "kb_resource_id": str(
                                object_ext.get("kb_resource_id")
                                or object_ext.get("kbResourceId")
                                or ""
                            ),
                            "kb_id": str(
                                object_ext.get("kb_id") or object_ext.get("kbId") or ""
                            ),
                            "kb_directory": kb_directory,
                            "term_id": str(
                                first_record.get("term_id")
                                or first_record.get("termId")
                                or ""
                            ),
                        },
                        ensure_ascii=False,
                    ),
                }
            ],
        )
    return ok(data=data)


async def _query_document_objects(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    """Query document terms using processing metadata filters."""
    base_id = str(
        params.pop("base_id", None) or params.pop("baseId", None) or DEFAULT_BASE_ID
    )
    request = QueryDocumentObjectsRequest.model_validate(params)
    try:
        page = await platform.query_document_objects(base_id, request=request)
    except DocumentLibraryError as exc:
        raise ValueError(str(exc)) from exc
    return ok(data=page.model_dump(by_alias=True, mode="json"))


async def _query_related_document_objects(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    """Query document terms connected by one incoming or outgoing relation."""
    base_id = str(
        params.pop("base_id", None) or params.pop("baseId", None) or DEFAULT_BASE_ID
    )
    request = QueryRelatedDocumentObjectsRequest.model_validate(params)
    page = await platform.query_related_document_objects(base_id, request=request)
    return ok(data=page.model_dump(by_alias=True, mode="json"))


async def _get_document_content_by_term_id(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    """Resolve a term and return its complete knowledge document content."""
    base_id = str(
        params.pop("base_id", None) or params.pop("baseId", None) or DEFAULT_BASE_ID
    )
    request = GetDocumentContentRequest.model_validate(params)
    try:
        result = await platform.get_document_content_by_term_id(
            base_id, term_id=request.term_id
        )
    except KbDocumentReadError as exc:
        raise ValueError(str(exc)) from exc
    return ok(data=result.model_dump(by_alias=True, mode="json"))


async def _search_knowledge_fragments(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    """Search knowledge chunks scoped to the supplied ontology objects."""
    base_id = str(
        params.pop("base_id", None) or params.pop("baseId", None) or DEFAULT_BASE_ID
    )
    request = SearchDocumentFragmentsRequest.model_validate(params)
    try:
        result = await platform.search_knowledge_fragments(base_id, request=request)
    except DocumentLibraryError as exc:
        raise ValueError(str(exc)) from exc
    return ok(data=result.model_dump(by_alias=True, mode="json"))


def _required_session_id(request: Request) -> str:
    session_id = request.headers.get("X-Session-Id", "").strip()
    if not session_id:
        raise ValueError("X-Session-Id header is required")
    return session_id


async def _discover_document_objects_async(
    platform: DatacloudPlatform, params: dict[str, Any], request: Request
) -> Any:
    """Accept a background document entity-discovery task."""
    session_id = _required_session_id(request)
    base_id = str(
        params.pop("base_id", None) or params.pop("baseId", None) or DEFAULT_BASE_ID
    )
    processing_request = DocumentAsyncProcessingRequest.model_validate(params)
    request.state.background_tasks.add_task(
        platform.process_document_discovery,
        base_id=base_id,
        session_id=session_id,
        request=processing_request,
    )
    accepted = DocumentAsyncProcessingAccepted(
        sessionId=session_id, taskType="documentDiscovery"
    )
    return ok(data=accepted.model_dump(by_alias=True, mode="json"))


async def _enrich_document_objects_async(
    platform: DatacloudPlatform, params: dict[str, Any], request: Request
) -> Any:
    """Accept a background document enrichment task."""
    session_id = _required_session_id(request)
    base_id = str(
        params.pop("base_id", None) or params.pop("baseId", None) or DEFAULT_BASE_ID
    )
    processing_request = DocumentAsyncProcessingRequest.model_validate(params)
    request.state.background_tasks.add_task(
        platform.process_document_enrichment,
        base_id=base_id,
        session_id=session_id,
        request=processing_request,
    )
    accepted = DocumentAsyncProcessingAccepted(
        sessionId=session_id, taskType="documentEnrichment"
    )
    return ok(data=accepted.model_dump(by_alias=True, mode="json"))


# ── Registry ──────────────────────────────────────────────────────────────────

REGISTRY: dict[str, Any] = {
    "invokeAction": _invoke_action,
    "queryDocumentObjects": _query_document_objects,
    "queryRelatedDocumentObjects": _query_related_document_objects,
    "getDocumentContentByTermId": _get_document_content_by_term_id,
    "searchKnowledgeFragments": _search_knowledge_fragments,
    "discoverDocumentObjectsAsync": _discover_document_objects_async,
    "enrichDocumentObjectsAsync": _enrich_document_objects_async,
}
