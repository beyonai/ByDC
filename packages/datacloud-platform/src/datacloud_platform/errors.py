"""datacloud_platform errors — re-exported from underlying SDKs.

All exception classes are re-exported from datacloud_data_sdk and
datacloud_knowledge so downstream packages import from a single place.
"""

from __future__ import annotations

from datacloud_data_sdk.exceptions import (
    ActionNotConfiguredError,
    ActionNotFoundError,
    ApiExecutionError,
    CannotAnswerError,
    DatacloudError,
    DataSourceUnavailableError,
    InvalidOntologyFormatError,
    ObjectNotFoundError,
    OntologyError,
    PermissionDeniedError,
    PlanError,
    ScriptExecutionError,
    SqlExecutionError,
    StepDependencyError,
    TermAmbiguousError,
    TermNotFoundError,
    TermResolutionError,
)

try:
    from datacloud_knowledge.file_store.errors import (
        BackendMisconfiguredError,
        FileNotFoundInStoreError,
        FileStoreError,
    )
except ImportError:  # pragma: no cover
    BackendMisconfiguredError = type(
        "BackendMisconfiguredError",
        (Exception,),
        {},
    )
    FileNotFoundInStoreError = type(
        "FileNotFoundInStoreError",
        (Exception,),
        {},
    )
    FileStoreError = type(
        "FileStoreError",
        (Exception,),
        {},
    )

try:
    from datacloud_knowledge.search.vector_validation import (
        TermVectorValidationError,
    )
except ImportError:  # pragma: no cover
    TermVectorValidationError = type(
        "TermVectorValidationError",
        (Exception,),
        {},
    )

__all__ = [
    "ActionNotConfiguredError",
    "ActionNotFoundError",
    "ApiExecutionError",
    "BackendMisconfiguredError",
    "CannotAnswerError",
    "DataSourceUnavailableError",
    "DatacloudError",
    "FileNotFoundInStoreError",
    "FileStoreError",
    "InvalidOntologyFormatError",
    "ObjectNotFoundError",
    "OntologyError",
    "PermissionDeniedError",
    "PlanError",
    "ScriptExecutionError",
    "SqlExecutionError",
    "StepDependencyError",
    "TermAmbiguousError",
    "TermNotFoundError",
    "TermResolutionError",
    "TermVectorValidationError",
]
