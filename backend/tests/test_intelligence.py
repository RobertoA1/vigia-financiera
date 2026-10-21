"""Offline contracts; fake model responses are simulated, never OpenAI verification."""
import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from langchain_core.runnables import RunnableLambda

from app.intelligence import AgentAssessment, analyze_evidence, analyze_role


def configured(**kwargs):
    values = dict(ai_enabled=True, openai_api_key="test-not-real", ai_reserved_calls=4)
    values.update(kwargs)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_disabled_and_missing_key_never_construct_model():
    factory = Mock(side_effect=AssertionError("must not call"))
    disabled = await analyze_evidence({}, settings=configured(ai_enabled=False, _ai_model_factory=factory))
    missing = await analyze_evidence({}, settings=configured(openai_api_key="", _ai_model_factory=factory))
    assert disabled["executed"] is False and disabled["reason"] == "disabled"
    assert missing["reason"] == "missing_api_key"
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_budget_guard_fails_closed():
    result = await analyze_evidence({}, settings=configured(ai_reserved_calls=0))
    assert result["reason"] == "daily_budget_not_reserved" and result["calls"] == 0


@pytest.mark.asyncio
async def test_simulated_four_lcel_agents_minimize_input_and_preserve_score():
    seen = []
    async def respond(prompt):
        seen.append(prompt.messages[-1].content)
        return AgentAssessment(summary="Indicadores requieren revisión.", evidence_codes=["brand"],
                               limitations=["Sin visita al destino"], recommendations=["Usar la aplicación oficial"],
                               suggest_escalation=True, additional_analysis=False, confidence="medium")
    class FakeModel:
        def with_structured_output(self, schema, **kwargs):
            assert schema is AgentAssessment and kwargs == {"method": "json_schema", "strict": True}
            return RunnableLambda(respond)
    evidence = {"domain": "bcp-ejemplo.test", "score": 80, "risk": "critical", "url": "https://test/?token=secret-value",
                "reputation": {"provider": "virustotal", "status": "complete", "checked_at": "2026-10-21T00:00:00Z", "stats": {"malicious": 8, "suspicious": 2, "harmless": 60, "raw_url": "private-reputation-url"}}, "user_id": "private-user", "history_summary": {"same_domain_24h": 3, "secret_history": "private-history"}, "indicators": [{"code": "brand", "title": "Suplantación", "detail": "sensitive-content"}]}
    result = await analyze_evidence(evidence, settings=configured(_ai_model_factory=lambda _: FakeModel()))
    assert result["status"] == "complete" and result["calls"] == 4
    assert len(result["agents"]) == 4 and evidence["score"] == 80
    assert all("secret-value" not in prompt and "private-user" not in prompt and "sensitive-content" not in prompt and "private-history" not in prompt for prompt in seen)
    assert all("same_domain_24h" in prompt and "virustotal" in prompt and "2026-10-21T00:00:00Z" in prompt and '"malicious": 8' in prompt and '"suspicious": 2' in prompt and '"harmless": 60' in prompt and "private-reputation-url" not in prompt for prompt in seen)
    # A caller cannot smuggle prior prose/URLs through the Langflow bridge.
    seen.clear()
    result = await analyze_role(evidence, role="context", previous={"context": {"summary": "https://sensitive/?token=private-prior", "evidence_codes": ["brand", "private-prior-code"], "additional_analysis": True}}, settings=configured(_ai_model_factory=lambda _: FakeModel(), ai_reserved_calls=1))
    assert result["status"] == "complete" and result["calls"] == 1
    assert all("private-prior" not in prompt for prompt in seen)



@pytest.mark.asyncio
async def test_invented_evidence_is_rejected_without_retry():
    fake = Mock()
    async def invented(_):
        return dict(summary="s", evidence_codes=["invented"], limitations=[], recommendations=[], suggest_escalation=False, additional_analysis=False, confidence="low")
    fake.with_structured_output.return_value = RunnableLambda(invented)
    result = await analyze_evidence({"indicators": []}, settings=configured(_ai_model_factory=lambda _: fake))
    assert result["status"] == "partial" and result["calls"] == 1 and not result["agents"]


@pytest.mark.asyncio
async def test_single_deadline_cancels_without_retry():
    async def slow(_):
        await asyncio.sleep(1)
    fake = Mock()
    fake.with_structured_output.return_value = RunnableLambda(slow)
    result = await analyze_evidence({}, settings=configured(_ai_model_factory=lambda _: fake, ai_timeout_seconds=.05))
    assert result["reason"] == "timeout" and result["calls"] == 1


@pytest.mark.asyncio
async def test_utf8_input_budget_is_bytes_and_no_cost_on_rejection():
    factory = Mock(side_effect=AssertionError("must not call"))
    evidence = {"domain": "test.example", "indicators": [{"code": "brand", "title": "🚩" * 200}]}
    result = await analyze_evidence(evidence, settings=configured(_ai_model_factory=factory, ai_max_input_chars=500))
    assert result["reason"] == "input_limit" and result["calls"] == 0
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_provider_error_does_not_expose_key_or_input():
    def factory(_):
        raise ValueError("API key test-not-real and private data")
    result = await analyze_evidence({}, settings=configured(_ai_model_factory=factory))
    assert result["reason"] == "provider_or_schema_error"
    assert "test-not-real" not in str(result) and "private data" not in str(result)


def test_langflow_bridge_requires_integration_key_and_disabled_is_explicit(client):
    payload = {"role": "context", "evidence": {"domain": "ejemplo.test", "score": 10, "risk": "low"}}
    endpoint = "/api/v1/automation/intelligence"
    assert client.post(endpoint, json=payload).status_code == 401
    headers = {"X-Webhook-Key": "test-webhook-key-only"}
    response = client.post(endpoint, json=payload, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["executed"] is False and response.json()["reason"] == "disabled"
    assert client.post(endpoint, json={**payload, "role": "shell"}, headers=headers).status_code == 422


def test_real_openai_adapter_builds_structured_chain_without_network():
    """Dependency compatibility only: constructing the client does not call OpenAI."""
    from app.intelligence import _make_model
    model = _make_model(configured())
    chain = model.with_structured_output(AgentAssessment, method="json_schema", strict=True)
    assert chain is not None
    assert model.max_retries == 0
    assert model.model_name == "gpt-6-mini"
