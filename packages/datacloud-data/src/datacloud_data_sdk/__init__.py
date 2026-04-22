"""datacloud-data-sdk: 本体驱动的数据查询与执行 SDK。"""

from importlib import import_module
from typing import Any

__all__ = [
    "OntologyLoader",
    "View",
    "Object",
    "Action",
    "Relation",
    "InvocationContext",
    "RequestContext",
    "get_current_context",
    "ResultFileStorage",
    "LocalResultFileStorage",
    "DatacloudError",
    "OntologyError",
    "ObjectNotFoundError",
    "ActionNotFoundError",
    "InvalidOntologyFormatError",
    "PlanError",
    "PlanGenerationError",
    "PlanValidationError",
    "CannotAnswerError",
    "ExecutionError",
    "ApiExecutionError",
    "SqlExecutionError",
    "ScriptExecutionError",
    "ActionNotConfiguredError",
    "DataSourceUnavailableError",
    "StepDependencyError",
    "AggregationError",
]

_SYMBOL_TO_MODULE = {
    "OntologyLoader": "datacloud_data_sdk.ontology.loader",
    "View": "datacloud_data_sdk.view",
    "Object": "datacloud_data_sdk.object",
    "Action": "datacloud_data_sdk.action",
    "Relation": "datacloud_data_sdk.relation",
    "InvocationContext": "datacloud_data_sdk.context",
    "RequestContext": "datacloud_data_sdk.context",
    "get_current_context": "datacloud_data_sdk.context",
    "ResultFileStorage": "datacloud_data_sdk.file_storage",
    "LocalResultFileStorage": "datacloud_data_sdk.file_storage",
    "DatacloudError": "datacloud_data_sdk.exceptions",
    "OntologyError": "datacloud_data_sdk.exceptions",
    "ObjectNotFoundError": "datacloud_data_sdk.exceptions",
    "ActionNotFoundError": "datacloud_data_sdk.exceptions",
    "InvalidOntologyFormatError": "datacloud_data_sdk.exceptions",
    "PlanError": "datacloud_data_sdk.exceptions",
    "PlanGenerationError": "datacloud_data_sdk.exceptions",
    "PlanValidationError": "datacloud_data_sdk.exceptions",
    "CannotAnswerError": "datacloud_data_sdk.exceptions",
    "ExecutionError": "datacloud_data_sdk.exceptions",
    "ApiExecutionError": "datacloud_data_sdk.exceptions",
    "SqlExecutionError": "datacloud_data_sdk.exceptions",
    "ScriptExecutionError": "datacloud_data_sdk.exceptions",
    "ActionNotConfiguredError": "datacloud_data_sdk.exceptions",
    "DataSourceUnavailableError": "datacloud_data_sdk.exceptions",
    "StepDependencyError": "datacloud_data_sdk.exceptions",
    "AggregationError": "datacloud_data_sdk.exceptions",
}


def __getattr__(name: str) -> Any:
    module_path = _SYMBOL_TO_MODULE.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_path)
    value = getattr(module, name)
    globals()[name] = value
    return value
