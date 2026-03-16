from datacloud_data.exceptions import (
    DatacloudError,
    ObjectNotFoundError,
    ActionNotFoundError,
    InvalidOntologyFormatError,
    PlanGenerationError,
    PlanValidationError,
    CannotAnswerError,
    ApiExecutionError,
    SqlExecutionError,
    ScriptExecutionError,
    ActionNotConfiguredError,
    DataSourceUnavailableError,
    AggregationError,
)


def test_error_hierarchy() -> None:
    assert issubclass(ObjectNotFoundError, DatacloudError)
    assert issubclass(CannotAnswerError, DatacloudError)
    assert issubclass(SqlExecutionError, DatacloudError)
    assert issubclass(ScriptExecutionError, DatacloudError)
    assert issubclass(ActionNotConfiguredError, DatacloudError)


def test_object_not_found_carries_code() -> None:
    err = ObjectNotFoundError("sales_bo")
    assert "sales_bo" in str(err)
    assert err.object_code == "sales_bo"


def test_plan_validation_error_carries_errors_list() -> None:
    err = PlanValidationError(["step_1: invalid sourceId", "aggregation: missing finalStepId"])
    assert len(err.errors) == 2


def test_script_execution_error_carries_details() -> None:
    err = ScriptExecutionError("calc_score", "NameError: x not defined", line_no=3)
    assert err.action_code == "calc_score"
    assert err.line_no == 3
    assert "NameError" in str(err)


def test_action_not_configured_error() -> None:
    err = ActionNotConfiguredError("empty_action")
    assert "empty_action" in str(err)
