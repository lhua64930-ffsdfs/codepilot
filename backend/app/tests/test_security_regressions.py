import pytest
from fastapi import HTTPException
from starlette.datastructures import URL
from starlette.requests import Request

from app.core.config import settings
from app.db.models import User
from app.services.authentication import authorize_api


@pytest.mark.asyncio
async def test_draft_approval_uses_asgi_path_even_if_reconstructed_url_differs():
    request = Request({"type": "http", "method": "POST", "path": "/api/action-drafts/example/confirm",
                       "query_string": b"", "headers": [], "scheme": "http", "server": ("test", 80)})
    request._url = URL("http://test/api/chat")
    with pytest.raises(HTTPException) as error:
        await authorize_api(request, user=User(name="developer", role="developer"), db=None)
    assert error.value.status_code == 403
    assert "draft:approve" in error.value.detail


def test_ragas_scorer_never_enables_pickle_disk_cache_or_multimodal_metrics(monkeypatch):
    from app.services.evals.ragas_runner import RagasCollectionsScorer, _ensure_ragas_compatibility
    _ensure_ragas_compatibility()
    import ragas.cache
    import ragas.llms
    def forbid_cache(*args, **kwargs):
        raise AssertionError("Untrusted persistent pickle cache must not be enabled")
    monkeypatch.setattr(ragas.cache.DiskCacheBackend, "__init__", forbid_cache)
    factory = ragas.llms.llm_factory
    seen = []
    def checked_factory(*args, **kwargs):
        seen.append(kwargs)
        return factory(*args, **kwargs)
    monkeypatch.setattr(ragas.llms, "llm_factory", checked_factory)
    monkeypatch.setattr(settings, "ragas_judge_api_key", "local-test-key")
    monkeypatch.setattr(settings, "ragas_judge_base_url", "https://example.invalid/v1")
    scorer = RagasCollectionsScorer()
    assert seen and seen[0]["cache"] is None
    assert set(scorer.metrics) == {"context_precision", "context_recall", "faithfulness", "answer_relevancy",
                                   "agent_goal_accuracy", "tool_call_accuracy", "tool_call_f1"}
