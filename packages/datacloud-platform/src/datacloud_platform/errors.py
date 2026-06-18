"""Unified exception hierarchy — re-exports from datacloud-data SDK.

All exceptions inherit from :class:`DatacloudError`, which serves as the common base
for catching any SDK-originated error.
"""

from __future__ import annotations

try:
    from datacloud_data_sdk.exceptions import (
        ActionNotConfiguredError,
        ActionNotFoundError,
        AggregationError,
        ApiExecutionError,
        CannotAnswerError,
        DatacloudError,
        DataSourceUnavailableError,
        ExecutionError,
        InvalidOntologyFormatError,
        KbExecutionError,
        ObjectNotFoundError,
        PermissionDeniedError,
        PermissionNotConfiguredError,
        PlanError,
        PlanGenerationError,
        PlanValidationError,
        ScriptExecutionError,
        SqlExecutionError,
        StepDependencyError,
        TermAmbiguousError,
        TermNotFoundError,
        TermResolutionError,
    )
except ImportError:
    # Fallback when datacloud-data is not installed.
    _Base = Exception
    DatacloudError = _Base
    OntologyError = _Base
    TermResolutionError = _Base
    TermNotFoundError = _Base
    TermAmbiguousError = _Base
    ObjectNotFoundError = _Base
    ActionNotFoundError = _Base
    InvalidOntologyFormatError = _Base
    PlanError = _Base
    PlanGenerationError = _Base
    PlanValidationError = _Base
    CannotAnswerError = _Base
    ExecutionError = _Base
    ApiExecutionError = _Base
    SqlExecutionError = _Base
    KbExecutionError = _Base
    ScriptExecutionError = _Base
    ActionNotConfiguredError = _Base
    PermissionNotConfiguredError = _Base
    PermissionDeniedError = _Base
    DataSourceUnavailableError = _Base
    StepDependencyError = _Base
    AggregationError = _Base

__all__ = [
    "ActionNotConfiguredError",
    "ActionNotFoundError",
    "AggregationError",
    "ApiExecutionError",
    "CannotAnswerError",
    "DataSourceUnavailableError",
    "DatacloudError",
    "ExecutionError",
    "InvalidOntologyFormatError",
    "KbExecutionError",
    "ObjectNotFoundError",
    "PermissionDeniedError",
    "PermissionNotConfiguredError",
    "PlanError",
    "PlanGenerationError",
    "PlanValidationError",
    "ScriptExecutionError",
    "SqlExecutionError",
    "StepDependencyError",
    "TermAmbiguousError",
    "TermNotFoundError",
    "TermResolutionError",
]
