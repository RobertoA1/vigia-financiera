"""Controlled fixtures only: no DNS lookup or connections to analyzed sites."""
from types import SimpleNamespace

import httpx
import pytest

from app.detection import evaluate_url, normalize_url, fetch_reputation, risk_for_score


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://bank.invalid/file", "gopher://bank.invalid/",
    "http://127.0.0.1/", "http://169.254.169.254/latest/meta-data/", "http://10.0.0.1/",
    "https://192.168.1.1/", "http://172.16.0.1/", "http://[::1]/", "http://[fc00::1]/",
    "http://[::ffff:127.0.0.1]/", "http://2130706433/", "http://0177.0.0.1/", "http://0x7f000001/",
    "http://localhost/", "http://intranet/", "http://bank.local/", "http://bank.internal/",
    "http://bank.invalid\\@private.invalid/", "http://bank.invalid\x00/", "https://u:password@bank.invalid/",
    "https://%31%32%37.0.0.1/", "http://[2001:db8::1]/", "https://bank.invalid:999999/",
    "http://１２７.０.０.１/", "http://bank.ｌｏｃａｌ/", "http://１０.０.０.１/",
])
def test_rejects_invalid_private_and_ambiguous(url):
    with pytest.raises(ValueError):
        normalize_url(url)


@pytest.mark.parametrize("domain", ["www.viabcp.com", "www.interbank.pe", "www.bbva.pe"])
def test_official_domain_match_is_boundary_aware(domain):
    assert evaluate_url("https://"+domain+"/login?token=secret")["score"] == 0
    fake = evaluate_url("https://"+domain+".control.invalid/login")
    assert fake["score"] >= 50
    assert "brand_impersonation" in [i["code"] for i in fake["indicators"]]


def test_minimizes_sensitive_components_and_scores_context():
    result = evaluate_url("https://bcp-control.invalid/secret-client-123?otp=123456&token=private#more-secrets")
    serialized = str(result)
    for secret in ("123456", "private", "secret-client-123", "more-secrets"):
        assert secret not in serialized
    assert result["url_display"] == "https://bcp-control.invalid/[ruta omitida]"
    assert result["score"] == 65


def test_redundant_brand_signals_are_not_added():
    result = evaluate_url("https://interbank-bbva-bcp-control.invalid/login")
    identity = [i for i in result["indicators"] if i["group"] == "identity"]
    assert len(identity) == 3
    assert result["score"] == 75  # Identity50 + context15 + structural10.


def test_unicode_mixed_scripts_are_explained_and_https_is_not_legitimacy():
    result = evaluate_url("https://interbаnk.invalid/login")  # Cyrillic а.
    assert result["score"] >= 50
    assert "mixed_scripts" in {i["code"] for i in result["indicators"]}
    assert "segur" in evaluate_url("https://example.com")["explanation"]


@pytest.mark.parametrize("score,risk", [(0,"low"),(24,"low"),(25,"moderate"),(49,"moderate"),(50,"high"),(74,"high"),(75,"critical"),(100,"critical")])
def test_thresholds(score,risk):
    assert risk_for_score(score) == risk


@pytest.mark.asyncio
@pytest.mark.parametrize("code,status", [(429,"rate_limited"),(404,"not_found"),(401,"unavailable"),(503,"unavailable")])
async def test_provider_failure_is_explicit_without_retry_storm(code,status):
    calls=[]
    def mock(request):
        calls.append(request)
        assert request.url.host == "www.virustotal.com"
        assert request.url.path == "/api/v3/domains/viabcp.com"
        return httpx.Response(code,json={})
    settings=SimpleNamespace(virustotal_api_key="test-only",virustotal_enabled=True,reputation_timeout_seconds=1)
    result=await fetch_reputation("viabcp.com",settings,transport=httpx.MockTransport(mock))
    assert result["status"] == status
    assert len(calls)==1


@pytest.mark.asyncio
async def test_external_report_has_provenance_and_no_url_submission():
    def mock(request):
        assert request.method=="GET" and not request.content
        return httpx.Response(200,json={"data":{"attributes":{"last_analysis_stats":{"malicious":3,"suspicious":0,"harmless":70},"last_analysis_date":1700000000}}})
    result=await fetch_reputation("bbva.pe",SimpleNamespace(virustotal_api_key="test-only",virustotal_enabled=True),transport=httpx.MockTransport(mock))
    assert result["status"]=="available"
    assert result["stats"]["malicious"]==3
    assert result["checked_at"] and result["evidence_at"]


@pytest.mark.asyncio
async def test_reanalysis_replaces_previous_reputation_instead_of_accumulating(monkeypatch):
    from app import provider_state
    from app.detection import enrich
    base = evaluate_url("https://viabcp.com")
    base["external_consent"] = True
    current = {"provider":"virustotal", "status":"available", "stats":{"malicious":3,"suspicious":0}, "checked_at":"2026-10-21T00:00:00Z"}
    monkeypatch.setattr(provider_state,"cached_reputation",lambda domain: dict(current))
    settings=SimpleNamespace(virustotal_enabled=True,virustotal_api_key="test-only")
    bad=await enrich(base,settings)
    bad_again=await enrich(bad,settings)
    assert bad_again["score"]==85
    assert len([i for i in bad_again["indicators"] if i["code"]=="reputation_detection"])==1
    current["stats"]={"malicious":0,"suspicious":0}
    clean=await enrich(bad_again,settings)
    assert clean["score"]==0 and clean["risk"]=="low"
    assert not clean["indicators"]
    assert "3 detecciones" not in clean["explanation"]
    assert len([s for s in clean["sources"] if s["provider"]=="virustotal"])==1
