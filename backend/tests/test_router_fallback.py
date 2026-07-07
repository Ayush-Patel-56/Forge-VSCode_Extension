# backend/tests/test_router_fallback.py
"""
Proves the ModelRouter 429 fallback chain with mocked provider clients
(no real API keys / network calls).

Run with:  python backend/tests/test_router_fallback.py
"""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

# backend/ must be on sys.path so `from router.model_router import ModelRouter`
# resolves the same way it does inside the backend package itself.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from router.model_router import ModelRouter  # noqa: E402


def _make_chunk(content: str) -> SimpleNamespace:
    """Shape a fake object like an openai streaming chunk."""
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content))])


class FakeAsyncStream:
    """Minimal async iterator yielding pre-baked fake chunks."""

    def __init__(self, contents: list[str]):
        self._contents = list(contents)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._contents:
            raise StopAsyncIteration
        return _make_chunk(self._contents.pop(0))


async def _raising_create(**kwargs):
    raise Exception("429 rate limit exceeded for this provider")


async def _make_success_create(chunks: list[str]):
    async def _create(**kwargs):
        return FakeAsyncStream(chunks)
    return _create


def _make_client(create_fn):
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create_fn)))


async def run_test() -> bool:
    router = ModelRouter()

    # Stub out DB writes so the test doesn't depend on / mutate the real sqlite db.
    router._log_usage = lambda *args, **kwargs: None  # type: ignore[method-assign]

    task_type = router._classify_task("hello there")
    candidates = router._get_candidates_with_default(task_type, None)
    assert len(candidates) >= 2, f"need at least 2 candidates to test fallback, got {candidates}"

    first_candidate, second_candidate = candidates[0], candidates[1]
    first_provider = first_candidate.split('/', 1)[0]
    second_provider = second_candidate.split('/', 1)[0]

    fake_content_chunks = ["Hel", "lo ", "world"]
    success_create = await _make_success_create(fake_content_chunks)

    stub_clients = {
        first_provider: _make_client(_raising_create),
        second_provider: _make_client(success_create),
    }

    def fake_get_client(provider: str):
        if provider not in stub_clients:
            raise AssertionError(f"unexpected provider requested: {provider}")
        return stub_clients[provider]

    router._get_client = fake_get_client  # type: ignore[method-assign]

    collected = []
    async for raw in router.stream(
        messages=[{'role': 'user', 'content': 'hello'}],
        model_id=None,
        context_chunks=[],
    ):
        payload = json.loads(raw)
        # stream() now also yields typed status/tool_call/tool_result events
        # (see model_router.py); only 'content' chunks matter for this test.
        if 'content' in payload:
            collected.append(payload['content'])

    streamed_text = ''.join(collected)

    ok = True

    # (a) fallback happened: the fake content from the second provider streamed through
    if streamed_text != ''.join(fake_content_chunks):
        print(f"FAIL: expected streamed content {fake_content_chunks!r}, got {streamed_text!r}")
        ok = False
    else:
        print(f"PASS: fallback streamed expected content: {streamed_text!r}")

    # (b) the first (429'd) candidate is marked rate-limited
    if first_candidate not in router._rate_limited:
        print(f"FAIL: expected {first_candidate!r} to be in _rate_limited, set={router._rate_limited}")
        ok = False
    else:
        print(f"PASS: {first_candidate!r} correctly marked rate-limited after 429")

    # (c) after the (short-circuited) clear delay, it is removed again
    await router._clear_rate_limit(first_candidate, 0)
    if first_candidate in router._rate_limited:
        print(f"FAIL: expected {first_candidate!r} to be cleared from _rate_limited")
        ok = False
    else:
        print(f"PASS: {first_candidate!r} cleared from _rate_limited after delay")

    return ok


def main() -> int:
    ok = asyncio.run(run_test())
    if ok:
        print("PASS: all fallback assertions succeeded")
        return 0
    print("FAIL: one or more fallback assertions failed")
    return 1


if __name__ == '__main__':
    sys.exit(main())
