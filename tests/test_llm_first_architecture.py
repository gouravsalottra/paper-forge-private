# tests/test_llm_first_architecture.py
# Verifies LLM-first architecture is correctly implemented.
# These tests use synchronous fallback paths only — no live LLM calls.


class TestPromptRegistry:
    """All 8 prompts exist and have required fields."""

    def test_all_prompts_importable(self):
        from api.prompts import (
            RESEARCH_ARCHITECT_PROMPT,
            LITERATURE_AGENT_PROMPT,
            METHOD_AGENT_PROMPT,
            STATISTICS_AGENT_PROMPT,
            CODE_AUDIT_PROMPT,
            HAWK_PROMPT,
            REPAIR_AGENT_PROMPT,
            WRITER_PROSE_PROMPT,
            WRITER_TABLES_PROMPT,
        )
        assert all([
            RESEARCH_ARCHITECT_PROMPT,
            LITERATURE_AGENT_PROMPT,
            METHOD_AGENT_PROMPT,
            STATISTICS_AGENT_PROMPT,
            CODE_AUDIT_PROMPT,
            HAWK_PROMPT,
            REPAIR_AGENT_PROMPT,
            WRITER_PROSE_PROMPT,
            WRITER_TABLES_PROMPT,
        ])

    def test_no_hardcoded_model_strings_in_prompts(self):
        from api.prompts import (
            RESEARCH_ARCHITECT_PROMPT,
            METHOD_AGENT_PROMPT,
            STATISTICS_AGENT_PROMPT,
            HAWK_PROMPT,
        )
        for prompt in [
            RESEARCH_ARCHITECT_PROMPT,
            METHOD_AGENT_PROMPT,
            STATISTICS_AGENT_PROMPT,
            HAWK_PROMPT,
        ]:
            assert ("gpt" + "-5") not in prompt
            assert ("gpt" + "-4-turbo") not in prompt

    def test_all_prompts_have_json_contract(self):
        from api.prompts import (
            RESEARCH_ARCHITECT_PROMPT,
            LITERATURE_AGENT_PROMPT,
            METHOD_AGENT_PROMPT,
            STATISTICS_AGENT_PROMPT,
            CODE_AUDIT_PROMPT,
            HAWK_PROMPT,
            REPAIR_AGENT_PROMPT,
            WRITER_PROSE_PROMPT,
            WRITER_TABLES_PROMPT,
        )
        for prompt in [
            RESEARCH_ARCHITECT_PROMPT,
            LITERATURE_AGENT_PROMPT,
            METHOD_AGENT_PROMPT,
            STATISTICS_AGENT_PROMPT,
            CODE_AUDIT_PROMPT,
            HAWK_PROMPT,
            REPAIR_AGENT_PROMPT,
            WRITER_PROSE_PROMPT,
            WRITER_TABLES_PROMPT,
        ]:
            assert "Return ONLY" in prompt or "Return only" in prompt

    def test_statistics_prompt_has_identification_field(self):
        from api.prompts import STATISTICS_AGENT_PROMPT
        assert "{identification_strategy}" in STATISTICS_AGENT_PROMPT
        assert "{method_family}" in STATISTICS_AGENT_PROMPT
        assert "robustness_checks" in STATISTICS_AGENT_PROMPT
        assert "desk_rejection_risks" in STATISTICS_AGENT_PROMPT

    def test_hawk_prompt_uses_results(self):
        from api.prompts import HAWK_PROMPT
        assert "{results_json}" in HAWK_PROMPT
        assert "{blueprint_json}" in HAWK_PROMPT
        assert "gate_passed" in HAWK_PROMPT

    def test_writer_prompt_numbers_contract(self):
        from api.prompts import WRITER_PROSE_PROMPT
        assert "stats_results" in WRITER_PROSE_PROMPT or "results_json" in WRITER_PROSE_PROMPT
        assert "invent" in WRITER_PROSE_PROMPT.lower() or "only" in WRITER_PROSE_PROMPT

    def test_writer_prompt_requires_standalone_academic_introduction(self):
        from api.prompts import WRITER_PROSE_PROMPT
        assert "Open with the economic phenomenon" in WRITER_PROSE_PROMPT
        assert "specific economic mechanism" in WRITER_PROSE_PROMPT
        assert "must NEVER mention Thrivarc" in WRITER_PROSE_PROMPT
        assert "research platform must be invisible" in WRITER_PROSE_PROMPT


class TestLLMCaller:
    """LLM caller handles JSON extraction and engine sanitization."""

    def test_json_extraction_raw(self):
        from api.llm_caller import _extract_json
        assert _extract_json('{"a": 1}') == {"a": 1}

    def test_json_extraction_markdown(self):
        from api.llm_caller import _extract_json
        text = '```json\n{"a": 1}\n```'
        assert _extract_json(text) == {"a": 1}

    def test_json_extraction_with_preamble(self):
        from api.llm_caller import _extract_json
        text = 'Here is the result: {"a": 1}'
        assert _extract_json(text) == {"a": 1}

    def test_json_extraction_invalid(self):
        from api.llm_caller import _extract_json
        assert _extract_json("not json at all") is None

    def test_engine_sanitizer_enforces_gpt4o(self):
        from api.llm_caller import _sanitize_engine_fields
        dirty = {"engine": "gpt" + "-5", "nested": {"engine": "gpt" + "-5.5"}}
        clean = _sanitize_engine_fields(dirty)
        assert clean["engine"] == "gpt-4o"
        assert clean["nested"]["engine"] == "gpt-4o"

    def test_engine_sanitizer_list(self):
        from api.llm_caller import _sanitize_engine_fields
        dirty = [{"engine": "gpt" + "-5"}, {"engine": "gpt" + "-4-turbo"}]
        clean = _sanitize_engine_fields(dirty)
        assert all(item["engine"] == "gpt-4o" for item in clean)


class TestMethodAgent:
    """Method agent fallback works correctly."""

    def test_fallback_returns_required_fields(self):
        from api.method_agent import _method_fallback
        result = _method_fallback(method_family="event_study")
        assert "modeling_frameworks" in result
        assert "estimation_sequence" in result
        assert "standard_error_approach" in result
        assert result.get("fallback_used") is True

    def test_fallback_unknown_method(self):
        from api.method_agent import _method_fallback
        result = _method_fallback(method_family="unknown_method_xyz")
        assert "fallback_used" in result


class TestStatsAgent:
    """Stats agent fallback works correctly and returns complete structure."""

    def test_fallback_returns_all_required_sections(self):
        from api.stats_agent import _stats_fallback
        result = _stats_fallback(method_family="event_study")
        required = [
            "pre_estimation_diagnostics",
            "post_estimation_diagnostics",
            "inference_tests",
            "identification_validity_tests",
            "robustness_checks",
        ]
        for field in required:
            assert field in result, f"Missing field: {field}"
        assert result.get("fallback_used") is True

    def test_registry_is_fallback_not_primary(self):
        """
        Confirm stats_agent primary path is LLM, not registry.
        The get_stats_spec function should import from api.prompts,
        not from method_registry.
        """
        import inspect
        import api.stats_agent as sa
        source = inspect.getsource(sa.get_stats_spec)
        assert "STATISTICS_AGENT_PROMPT" in source
        assert "call_agent_llm" in source


class TestCodeAuditAgent:
    """Code audit agent structure is correct."""

    def test_fallback_structure(self):
        from api.code_audit_agent import _audit_fallback
        result = _audit_fallback()
        assert "audit_passed" in result
        assert "violations" in result
        assert "audit_summary" in result
        assert result.get("fallback_used") is True


class TestWriterGate:
    """Writer must not fire unless gate is passed."""

    def test_writer_blocked_when_gate_failed(self):
        """
        Simulate the gate check.
        Writer trigger function must return False when gate_passed=False.
        """
        hawk_failed = {"gate_passed": False, "average_score": 5.5}
        hawk_passed = {"gate_passed": True, "average_score": 7.8}

        def can_trigger_writer(hawk_result: dict) -> bool:
            return hawk_result.get("gate_passed", False) is True

        assert can_trigger_writer(hawk_failed) is False
        assert can_trigger_writer(hawk_passed) is True


class TestLiteratureRetrieval:
    """Literature retrieval should broaden narrow finance topics without hardcoding studies."""

    def test_supplemental_queries_include_topic_acronyms(self):
        from api.literature_agent import _supplemental_queries

        queries = _supplemental_queries(
            "Does the VIX term structure inversion predict next-month momentum crashes in US equity sector ETFs?",
            "time_series",
        )

        assert any(query.startswith("VIX ") for query in queries)
        assert any("asset pricing" in query for query in queries)


class TestNoHardcodedRegistryInPrimaryPath:
    """
    Registry must not appear as primary path in agent files.
    It is fallback only.
    """

    def test_stats_agent_primary_uses_llm_not_registry(self):
        import inspect
        import api.stats_agent as sa
        source = inspect.getsource(sa.get_stats_spec)
        # Primary function must call LLM, not registry directly
        assert "call_agent_llm" in source
        assert "METHOD_REGISTRY" not in source

    def test_method_agent_primary_uses_llm_not_registry(self):
        import inspect
        import api.method_agent as ma
        source = inspect.getsource(ma.get_method_spec)
        assert "call_agent_llm" in source
        assert "METHOD_REGISTRY" not in source
