"""
Proves budget-aware routing and real cost/token accounting on ModelRouter,
with mocked provider clients and stubbed DB writes (no real API keys / network
calls, no dependency on main.py).

Run with:  python backend/tests/test_budget_routing.py
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


def _make_client(create_fn):
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create_fn)))


def _make_router() -> ModelRouter:
    router = ModelRouter()
    # Stub out DB writes so tests don't depend on / mutate the real sqlite db.
    router._log_usage = lambda *args, **kwargs: None  # type: ignore[method-assign]
    # Stub out the model-cost DB lookup so tests are fully isolated.
    router._model_costs = {}
    router._model_costs_loaded = True
    return router


def test_budget_near_limit_restricts_to_free() -> bool:
    router = _make_router()
    router._daily_budget_usd = 1.0
    router._today_cost_usd = 0.95

    ok = True

    if not router._should_use_free_only():
        print("FAIL: expected _should_use_free_only() to be True at 95% of a $1.00 budget")
        ok = False
    else:
        print("PASS: _should_use_free_only() is True near the budget limit")

    for task_type in ('quick', 'coding', 'long', 'vision'):
        candidates = router._get_candidates(task_type, None)
        non_free = [c for c in candidates if not router._is_free(c)]
        if non_free:
            print(f"FAIL: expected only free models for task {task_type!r} near budget, found non-free: {non_free}")
            ok = False
        else:
            print(f"PASS: candidates for task {task_type!r} restricted to free models near budget: {candidates}")

    return ok


def test_zero_budget_means_unlimited() -> bool:
    router = _make_router()
    router._daily_budget_usd = 0
    router._today_cost_usd = 500.0  # arbitrarily high spend

    ok = True
    if router._should_use_free_only():
        print("FAIL: expected _should_use_free_only() to be False when budget is 0 (unlimited)")
        ok = False
    else:
        print("PASS: budget of 0 means unlimited (_should_use_free_only() is False)")
    return ok


async def _run_cost_math_test() -> bool:
    router = _make_router()

    task_type = router._classify_task("hello there")
    candidates = router._get_candidates_with_default(task_type, None)
    streamed_candidate = candidates[0]
    provider = streamed_candidate.split('/', 1)[0]

    fake_content_chunks = ["Hel", "lo ", "world"]  # 8 chars total -> tokens_out = 8 // 4 = 2

    async def _create(**kwargs):
        return FakeAsyncStream(fake_content_chunks)

    router._get_client = lambda p: _make_client(_create)  # type: ignore[method-assign]

    # Inject a known cost entry for the model that will actually stream.
    cost_in, cost_out = 0.001, 0.002
    router._model_costs[streamed_candidate] = (cost_in, cost_out)

    messages = [{'role': 'user', 'content': 'hello'}]
    expected_tokens_in = sum(len(m['content']) for m in messages) // 4
    # tokens_out is accumulated per streamed chunk (matches router.stream's own
    # per-delta `len(delta) // 4`), not floor-divided on the joined total.
    expected_tokens_out = sum(len(c) // 4 for c in fake_content_chunks)
    expected_cost = expected_tokens_in / 1000 * cost_in + expected_tokens_out / 1000 * cost_out

    tokens_before = router._today_tokens
    cost_before = router._today_cost_usd

    collected = []
    async for raw in router.stream(messages=messages, model_id=None, context_chunks=[]):
        payload = json.loads(raw)
        collected.append(payload['content'])

    streamed_text = ''.join(collected)

    ok = True

    if streamed_text != ''.join(fake_content_chunks):
        print(f"FAIL: expected streamed content {fake_content_chunks!r}, got {streamed_text!r}")
        ok = False
    else:
        print(f"PASS: streamed expected content via {streamed_candidate!r}: {streamed_text!r}")

    tokens_delta = router._today_tokens - tokens_before
    if tokens_delta != expected_tokens_in + expected_tokens_out:
        print(f"FAIL: expected _today_tokens to grow by {expected_tokens_in + expected_tokens_out}, grew by {tokens_delta}")
        ok = False
    else:
        print(f"PASS: _today_tokens grew by expected amount ({tokens_delta})")

    cost_delta = router._today_cost_usd - cost_before
    if abs(cost_delta - expected_cost) > 1e-9:
        print(f"FAIL: expected _today_cost_usd to grow by ~{expected_cost}, grew by {cost_delta}")
        ok = False
    else:
        print(f"PASS: _today_cost_usd grew by expected amount (~{cost_delta:.6f})")

    return ok


def main() -> int:
    ok = True
    ok &= test_budget_near_limit_restricts_to_free()
    ok &= test_zero_budget_means_unlimited()
    ok &= asyncio.run(_run_cost_math_test())

    if ok:
        print("PASS: all budget/cost accounting assertions succeeded")
        return 0
    print("FAIL: one or more budget/cost accounting assertions failed")
    return 1


if __name__ == '__main__':
    sys.exit(main())
