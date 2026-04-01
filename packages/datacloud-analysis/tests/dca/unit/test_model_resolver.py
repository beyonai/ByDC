from datacloud_analysis.orchestration.shared.model_resolver import resolve_reasoning_model_spec


def test_resolve_reasoning_model_spec_accepts_case_insensitive_prefix() -> None:
    spec = resolve_reasoning_model_spec("OpenAI:Qwen/Qwen3-235B-A22B")
    assert spec["model"] == "Qwen/Qwen3-235B-A22B"
    assert spec["model_provider"] == "openai"
    assert spec["provider_prefixed"] is True
